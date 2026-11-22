import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date
import os
from pathlib import Path
import sqlite3
from threading import Event

import pytest
from fastapi import HTTPException

from app import database, sqlite_ops
from app.services import multiple_choice
from conftest import deck


def test_backup_reads_committed_snapshot_during_wal_write(tmp_path):
    live = tmp_path / 'live.db'
    with closing(sqlite3.connect(live)) as connection:
        assert connection.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
        connection.execute('CREATE TABLE pairs (first INTEGER NOT NULL, second INTEGER NOT NULL)')
        connection.execute('INSERT INTO pairs VALUES (0, 0)')
        connection.commit()

    writing, release = Event(), Event()

    def writer():
        with closing(sqlite3.connect(live)) as connection:
            connection.execute('UPDATE pairs SET first=1')
            writing.set()
            assert release.wait(10)
            connection.execute('UPDATE pairs SET second=1')
            connection.commit()

    before = tmp_path / 'snapshot.db'
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(writer)
        try:
            assert writing.wait(5)
            sqlite_ops.online_snapshot(live, before)
            with closing(sqlite_ops.read_only(before)) as connection:
                assert connection.execute('SELECT * FROM pairs').fetchone() == (0, 0)
        finally:
            release.set()
        future.result(timeout=5)

    after = tmp_path / 'after.db'
    sqlite_ops.online_snapshot(live, after)
    with closing(sqlite_ops.read_only(after)) as connection:
        assert connection.execute('SELECT * FROM pairs').fetchone() == (1, 1)


def test_restore_preserves_decks_and_revokes_only_restored_sessions(client, tmp_path):
    deck(client)
    live = Path(client.database_url.removeprefix('sqlite:///'))
    snapshot, output = tmp_path / 'snapshot.db', tmp_path / 'recovered.db'
    sqlite_ops.online_snapshot(live, snapshot)
    with pytest.raises(ValueError, match='never'):
        sqlite_ops.restore(snapshot, live, live)
    sqlite_ops.restore(snapshot, output, live)
    with pytest.raises(FileExistsError):
        sqlite_ops.restore(snapshot, output, live)
    with closing(sqlite_ops.read_only(output)) as restored:
        assert restored.execute('SELECT count(*) FROM users').fetchone() == (1,)
        assert restored.execute('SELECT count(*) FROM decks').fetchone() == (1,)
        assert restored.execute('SELECT count(*) FROM flashcards').fetchone() == (1,)
        assert restored.execute('SELECT count(*) FROM auth_sessions').fetchone() == (0,)
        assert restored.execute('PRAGMA foreign_key_check').fetchall() == []
    assert client.get('/api/auth/me').status_code == 200


def test_backup_retains_verified_daily_copy_and_does_not_upload_invalid_data(tmp_path, monkeypatch):
    source = tmp_path / 'source.db'
    directory = tmp_path / 'backups'
    old_day, day = date(2026, 1, 1), date(2026, 1, 20)
    with closing(sqlite3.connect(source)) as connection:
        connection.execute('CREATE TABLE data (value TEXT)')
    monkeypatch.delenv('RESTIC_REPOSITORY_FILE', raising=False)
    monkeypatch.delenv('RESTIC_REPOSITORY', raising=False)
    old = sqlite_ops.save_backup(source, directory, 14, daily=old_day)
    os.utime(old, (1, 1))
    commands = []
    monkeypatch.setenv('RESTIC_REPOSITORY', 'synthetic-test-repository')
    monkeypatch.setattr(sqlite_ops, 'restic', lambda *args: commands.append(args))
    first = sqlite_ops.save_backup(source, directory, 14, daily=day)
    assert sqlite_ops.save_backup(source, directory, 14, daily=day) == first
    assert not old.exists()
    assert [cmd[0] for cmd in commands] == ['backup', 'forget', 'backup', 'forget']
    first.write_bytes(b'not a database')
    with pytest.raises(sqlite3.DatabaseError):
        sqlite_ops.save_backup(source, directory, 14, daily=day)
    assert len(commands) == 4


def make_legacy(path):
    with closing(sqlite3.connect(path)) as db:
        db.execute('CREATE TABLE decks (id INTEGER PRIMARY KEY, title TEXT NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)')
        db.execute("INSERT INTO decks VALUES(1, 'Preserved','2026-01-01','2026-01-01')")
        db.commit()


def test_concurrent_migrations_take_one_snapshot_and_advance_version(tmp_path):
    path = tmp_path / 'legacy.db'
    make_legacy(path)
    engines = [database.make_engine(f'sqlite:///{path.as_posix()}') for _ in range(2)]
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(database.init_database, engine) for engine in engines]
            for future in futures:
                future.result(timeout=15)
        snapshots = list((tmp_path / '.migration-backups' / path.name).glob('*.db'))
        assert len(snapshots) == 1
        with closing(sqlite_ops.read_only(snapshots[0])) as old:
            assert old.execute('PRAGMA user_version').fetchone() == (0,)
            assert old.execute('SELECT title FROM decks').fetchone() == ('Preserved',)
        with closing(sqlite_ops.read_only(path)) as upgraded:
            assert upgraded.execute('PRAGMA user_version').fetchone() == (database.SCHEMA_VERSION,)
            assert upgraded.execute('SELECT visibility FROM decks').fetchone() == ('private',)
    finally:
        for engine in engines:
            engine.dispose()


def test_migration_failures_leave_old_schema_and_data_intact(tmp_path, monkeypatch):
    path = tmp_path / 'legacy.db'
    make_legacy(path)
    engine = database.make_engine(f'sqlite:///{path.as_posix()}')
    try:
        with monkeypatch.context() as patch:
            def failed_snapshot(_):
                raise OSError('no space')
            patch.setattr(database, 'pre_migration_snapshot', failed_snapshot)
            with pytest.raises(RuntimeError, match='pre-migration backup'):
                database.init_database(engine)

        def failed_upgrade(connection):
            connection.exec_driver_sql("UPDATE decks SET title='Interrupted'")
            raise sqlite3.OperationalError('synthetic DDL failure')

        monkeypatch.setattr(database, 'upgrade_baseline', failed_upgrade)
        with pytest.raises(RuntimeError, match='applying schema version'):
            database.init_database(engine)
        with closing(sqlite_ops.read_only(path)) as db:
            assert db.execute('PRAGMA user_version').fetchone() == (0,)
            assert db.execute('SELECT title FROM decks').fetchone() == ('Preserved',)
            assert db.execute("SELECT name FROM sqlite_schema WHERE name='users'").fetchone() is None
        backups = list((tmp_path / '.migration-backups' / path.name).glob('*.db'))
        assert len(backups) == 1
        sqlite_ops.verify_snapshot(backups[0])
    finally:
        engine.dispose()


def test_in_process_queue_admission_and_duplicate_jobs(monkeypatch):
    monkeypatch.setenv('MCQ_MAX_PENDING_JOBS', '2')
    monkeypatch.setenv('MCQ_MAX_PENDING_PER_USER', '1')
    monkeypatch.setattr(multiple_choice, 'recover_interrupted', lambda: None)

    async def scenario():
        jobs = multiple_choice.PreparationJobs()
        queued = []
        release = asyncio.Event()
        persisting, committed = Event(), Event()

        async def hold(session_id, attempt):
            queued.append((session_id, attempt))
            await release.wait()

        monkeypatch.setattr(jobs, '_prepare', hold)
        persistent = []

        def persist(identity):
            if identity == 'first':
                persisting.set()
                assert committed.wait(5)
            persistent.append(identity)
            return {'id': identity}, 1

        first = asyncio.create_task(jobs.submit(1, persist, 'first'))
        try:
            assert await asyncio.to_thread(persisting.wait, 3)
            with pytest.raises(HTTPException) as own:
                await jobs.submit(1, persist, 'duplicate-user')
            assert own.value.status_code == 429 and own.value.headers['Retry-After']
            assert (await jobs.submit(2, persist, 'second'))['id'] == 'second'
            with pytest.raises(HTTPException) as saturated:
                await jobs.submit(3, persist, 'third')
            assert saturated.value.status_code == 429
        finally:
            committed.set()
            await first
        jobs.start('first', 1, 1)
        await asyncio.sleep(0)
        assert sorted(queued) == [('first', 1), ('second', 1)]
        assert 'duplicate-user' not in persistent and 'third' not in persistent
        await jobs.cancel('first')
        assert (await jobs.submit(3, persist, 'third'))['id'] == 'third'
        await jobs.stop()
        assert not jobs.tasks and not jobs.current
        with pytest.raises(HTTPException) as closing_queue:
            await jobs.submit(4, persist, 'shutdown')
        assert closing_queue.value.status_code == 503

    asyncio.run(scenario())
