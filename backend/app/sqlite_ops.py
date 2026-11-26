"""Online SQLite snapshots, verified recovery copies, and optional encrypted restic shipping."""
import argparse
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

from sqlalchemy.engine import make_url

SNAPSHOT_PATTERN = re.compile(r'(?:daily-\d{4}-\d{2}-\d{2}|manual-\d{8}T\d{6}-[0-9a-f]{8})\.db')
BACKUP_TIMEOUT = 900


def configured_database():
    url = make_url(os.getenv('DATABASE_URL', 'sqlite:///./data/queezo.db'))
    if url.get_backend_name() != 'sqlite' or not url.database or url.database == ':memory:':
        raise ValueError('Backup requires a file-backed SQLite DATABASE_URL.')
    return Path(url.database).resolve()


def read_only(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=5)


def verify_snapshot(path):
    deadline = time.monotonic() + BACKUP_TIMEOUT
    with closing(read_only(path)) as connection:
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        if connection.execute('PRAGMA integrity_check').fetchone() != ('ok',):
            raise ValueError('SQLite snapshot failed its integrity check.')
        if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise ValueError('SQLite snapshot failed its foreign-key check.')


def online_snapshot(source, destination, *, revoke_sessions=False):
    """Take a consistent snapshot and publish it only after validation."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if any(Path(str(destination) + suffix).exists() for suffix in ('', '-wal', '-shm', '-journal')):
        raise FileExistsError('Choose a new output path with no SQLite sidecar files.')
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    deadline = time.monotonic() + BACKUP_TIMEOUT

    def check_deadline(*_):
        if time.monotonic() > deadline:
            raise TimeoutError('SQLite snapshot timed out.')

    handle, name = tempfile.mkstemp(prefix='.sqlite-snapshot-', dir=destination.parent)
    os.close(handle)
    temporary = Path(name)
    try:
        with closing(read_only(source)) as original, closing(sqlite3.connect(temporary)) as copy:
            original.backup(copy, pages=256, progress=check_deadline, sleep=0.05)
            if copy.execute('PRAGMA journal_mode=DELETE').fetchone()[0] != 'delete':
                raise ValueError('Could not make a self-contained SQLite snapshot.')
            if revoke_sessions:
                copy.execute('PRAGMA foreign_keys=ON')
                if copy.execute("SELECT 1 FROM sqlite_master WHERE name='auth_sessions' AND type='table'").fetchone():
                    copy.execute('DELETE FROM auth_sessions')
                    copy.commit()
        verify_snapshot(temporary)
        with temporary.open('rb') as file:
            os.fsync(file.fileno())
        # Same-directory hard link publishes a complete file without overwriting a concurrent backup.
        os.link(temporary, destination)
        if os.name == 'posix':
            directory = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        return destination
    finally:
        for suffix in ('', '-journal', '-wal', '-shm'):
            Path(str(temporary) + suffix).unlink(missing_ok=True)


def pre_migration_snapshot(connection):
    source = next((Path(row[2]) for row in connection.execute('PRAGMA database_list')
                   if row[1] == 'main' and row[2]), None)
    if source is None:
        raise ValueError('Migrating an existing database requires a file-backed SQLite database.')
    directory = source.parent / '.migration-backups' / source.name
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    snapshot = online_snapshot(source, directory / f'pre-migration-{stamp}-{uuid4().hex[:8]}.db')
    # Prevent a failed startup or operator retry from filling the volume with copies.
    for old in sorted(directory.glob('pre-migration-*.db'), reverse=True)[3:]:
        old.unlink()
    return snapshot


def restore(source, output, live):
    if Path(output).resolve() == Path(live).resolve():
        raise ValueError('Restore must target a recovery file, never the configured live database.')
    verify_snapshot(source)
    return online_snapshot(source, output, revoke_sessions=True)


def restic(*arguments):
    # Repository endpoints and credentials may appear in tool error text.
    try:
        subprocess.run(['restic', *arguments], check=True, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError('Encrypted backup or retention failed. Check the repository and permissions.') from None


def save_backup(source, directory, retention, *, daily=None):
    directory = Path(directory)
    if daily:
        filename = f'daily-{daily.isoformat()}.db'
    else:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
        filename = f'manual-{stamp}-{uuid4().hex[:8]}.db'
    snapshot = directory / filename
    try:
        online_snapshot(source, snapshot)
    except FileExistsError:
        if not daily or not snapshot.is_file():
            raise
        # A manual run or a previous failed upload may have produced today's copy.
        verify_snapshot(snapshot)
    cutoff = time.time() - retention * 86400
    for candidate in directory.iterdir():
        if candidate != snapshot and SNAPSHOT_PATTERN.fullmatch(candidate.name) and candidate.is_file():
            if candidate.stat().st_mtime < cutoff:
                candidate.unlink()
    if os.getenv('RESTIC_REPOSITORY') or os.getenv('RESTIC_REPOSITORY_FILE'):
        restic('backup', '--host', 'queezo', '--tag', 'queezo-sqlite', str(snapshot))
        restic('forget', '--host', 'queezo', '--tag', 'queezo-sqlite',
               '--group-by', 'host,tags', '--keep-within', f'{retention}d', '--keep-last', '1', '--prune')
    return snapshot


def publish_success(marker, day):
    temporary = marker.with_name(f'.last-success-{uuid4().hex}')
    try:
        temporary.write_text(day.isoformat(), encoding='ascii')
        temporary.replace(marker)
    finally:
        temporary.unlink(missing_ok=True)


def schedule(source, directory, retention, status_directory=None):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    marker = directory / '.last-success'
    while True:
        today = datetime.now(timezone.utc).date()
        try:
            try:
                last = date.fromisoformat(marker.read_text(encoding='ascii').strip())
            except (FileNotFoundError, ValueError):
                last = None
            if last != today:
                snapshot = save_backup(source, directory, retention, daily=today)
                publish_success(marker, today)
                print(f'Verified daily snapshot: {snapshot.name}', flush=True)
            if status_directory is not None:
                publish_success(status_directory / marker.name, today)
        except (OSError, RuntimeError, ValueError, sqlite3.Error):
            print('Daily database backup failed. Check storage and backup configuration; retrying within an hour.',
                  file=sys.stderr, flush=True)
            time.sleep(3600)
            continue
        tomorrow = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        time.sleep(max(1, (tomorrow - datetime.now(timezone.utc)).total_seconds()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('backup')
    commands.add_parser('schedule')
    commands.add_parser('migrate')
    verify = commands.add_parser('verify')
    verify.add_argument('snapshot', type=Path)
    recovery = commands.add_parser('restore')
    recovery.add_argument('snapshot', type=Path)
    recovery.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'verify':
            verify_snapshot(args.snapshot)
            print('SQLite snapshot passed integrity and foreign-key checks.')
        elif args.command == 'restore':
            restore(args.snapshot, args.output, configured_database())
            print('Verified recovery copy created. Existing login sessions were removed from the copy.')
        elif args.command == 'migrate':
            from app.database import init_database
            try:
                init_database()
            except RuntimeError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            print('SQLite schema is current.')
        else:
            directory = Path(os.getenv('BACKUP_DIRECTORY', '/backups'))
            retention = int(os.getenv('BACKUP_RETENTION_DAYS', '14'))
            if not 1 <= retention <= 365:
                raise ValueError('BACKUP_RETENTION_DAYS must be between 1 and 365.')
            if args.command == 'backup':
                print('Verified snapshot:', save_backup(configured_database(), directory, retention).name)
            else:
                status_directory = os.getenv('BACKUP_STATUS_DIRECTORY')
                schedule(configured_database(), directory, retention, Path(status_directory) if status_directory else None)
        return 0
    except (OSError, RuntimeError, ValueError, sqlite3.Error):
        print('Database operation failed. Check the paths, permissions, backup configuration and application logs.',
              file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
