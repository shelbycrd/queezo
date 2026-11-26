import threading
from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient

from app.auth.service import create_user
from app.database import write_transaction
from app.main import app
from app.models import (AchievementCredit, Flashcard, MultipleChoiceSession, RoomMember, RoomQuestion, RoomSession,
                        StudyRoom, User, UserAchievement, utcnow)
from app.services import achievements, room_study
from conftest import deck, review

PASSWORD = 'synthetic achievement passphrase'


def make_user(client, name):
    with client.factory.begin() as db:
        return create_user(db, f'{name}@example.com', PASSWORD, username=name).id


def sign_in(name):
    browser = TestClient(app)
    response = browser.post('/api/auth/login', json={'email':f'{name}@example.com', 'password':PASSWORD})
    assert response.status_code == 200, response.text
    browser.headers['x-csrf-token'] = response.json()['csrf_token']
    return browser


def row(client, user_id, key):
    with client.factory() as db:
        return db.get(UserAchievement, (user_id, key))


def record(client, user_id, event, **kwargs):
    with write_transaction(client.factory) as db:
        achievements.record(db, user_id, event, **kwargs)


def own(browser):
    return {item['key']: item for item in browser.get('/api/profiles/me').json()['achievements']}


# Deck Master -----------------------------------------------------------------------------

def test_deck_master_counts_original_decks_only_and_survives_deletion(client):
    user_id = client.test_user_id
    created = [deck(client, 0) for _ in range(9)]
    assert own(client)['deck_master'] | {'progress': 9, 'unlocked': False} == own(client)['deck_master']
    other = make_user(client, 'sharer')
    sharer = sign_in('sharer')
    shared = sharer.post('/api/decks', json={'title':'Shared deck', 'visibility':'unlisted'}).json()
    assert client.post(f"/api/shared/decks/{shared['share_token']}/copy").status_code == 201  # copies never count
    assert client.patch(f'/api/decks/{created[0]}', json={'title':'Renamed'}).status_code == 200  # edits never count
    assert client.delete(f'/api/decks/{created[1]}').status_code in (200, 204)  # deletion keeps lifetime progress
    assert row(client, user_id, 'deck_master').progress == 9 and row(client, user_id, 'deck_master').unlocked_at is None
    tenth = deck(client, 0)  # threshold boundary: exactly the 10th original deck unlocks
    unlocked = row(client, user_id, 'deck_master')
    assert unlocked.progress == 10 and unlocked.unlocked_at is not None
    assert client.delete(f'/api/decks/{tenth}').status_code in (200, 204)
    deck(client, 0)
    assert row(client, user_id, 'deck_master').progress == 10  # permanent; progress stops once unlocked
    assert row(client, user_id, 'deck_master').unlocked_at == unlocked.unlocked_at
    assert row(client, other, 'deck_master').progress == 1


def test_concurrent_events_count_exactly_once_each(client):
    user_id = client.test_user_id
    barrier = threading.Barrier(8)

    def create():
        barrier.wait()
        record(client, user_id, 'deck_created')

    threads = [threading.Thread(target=create) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert row(client, user_id, 'deck_master').progress == 8
    with pytest.raises(RuntimeError):
        with write_transaction(client.factory) as db:  # a failed action rolls its progress back
            achievements.record(db, user_id, 'deck_created')
            raise RuntimeError('action failed')
    assert row(client, user_id, 'deck_master').progress == 8


# Studious -----------------------------------------------------------------------------------

def test_studious_daily_window_follows_manila_and_resets_lazily(client):
    user_id = client.test_user_id
    late = datetime(2026, 11, 20, 15, 59, 59)  # 23:59:59 in Manila
    for _ in range(9):
        record(client, user_id, 'study_completed', at=late)
    record(client, user_id, 'study_completed', at=late + timedelta(seconds=1))  # 00:00 next Manila day
    current = row(client, user_id, 'studious')
    assert (current.progress, current.period_date, current.unlocked_at) == (1, date(2026, 11, 21), None)
    record(client, user_id, 'study_completed', at=late)  # a late-processed earlier day cannot reopen it
    assert row(client, user_id, 'studious').progress == 1
    for _ in range(9):
        record(client, user_id, 'study_completed', at=late + timedelta(hours=2))
    assert row(client, user_id, 'studious').unlocked_at is not None
    record(client, user_id, 'study_completed', at=late + timedelta(days=3))
    assert row(client, user_id, 'studious').progress == 10  # permanent


def test_owner_sees_zero_daily_progress_after_the_day_changes(client):
    record(client, client.test_user_id, 'study_completed', at=utcnow() - timedelta(days=2))
    assert own(client)['studious']['progress'] == 0
    record(client, client.test_user_id, 'study_completed')
    assert own(client)['studious']['progress'] == 1


def test_classic_completion_counts_once_and_repeats_on_the_same_deck_count(client):
    deck_id = deck(client, 1)
    for expected in (1, 2):
        state = client.post(f'/api/decks/{deck_id}/study').json()
        while state['status'] == 'active':
            state = review(client, state)
        assert client.post(f"/api/study/{state['id']}/exit").status_code == 200  # no second transition
        assert row(client, client.test_user_id, 'studious').progress == expected
    exited = client.post(f'/api/decks/{deck_id}/study').json()
    assert client.post(f"/api/study/{exited['id']}/exit").status_code == 200  # abandoned sessions do not count
    assert row(client, client.test_user_id, 'studious').progress == 2


def test_multiple_choice_completion_is_counted_on_the_transition_only(client):
    from app.services import multiple_choice

    deck_id = deck(client, 1)
    now = utcnow()
    with write_transaction(client.factory) as db:
        sessions = [MultipleChoiceSession(id=str(uuid4()), owner_id=client.test_user_id, deck_id=deck_id, deck_title='D',
                                          status=status, prepare_until=now, expires_at=now)
                    for status in ('active', 'cancelled', 'active')]
        db.add_all(sessions)
        db.flush()
        multiple_choice._mark_completed(db, sessions[0], now)
        multiple_choice._mark_completed(db, sessions[0], now)  # repeated completion processing
        multiple_choice._mark_completed(db, sessions[1], now)  # cancelled sessions never count
    assert row(client, client.test_user_id, 'studious').progress == 1


# Hoster ---------------------------------------------------------------------------------------

def hosted_room(db, host, guest, *, played=True, starting_host=None, keep_host=True):
    room = StudyRoom(id=str(uuid4()), host_id=host, phase='question')
    db.add(room)
    db.flush()
    for user_id in {host, guest, starting_host or host}:
        if user_id != (starting_host or host) or keep_host:
            db.add(RoomMember(room_id=room.id, user_id=user_id, seen_at=utcnow()))
    session = RoomSession(id=str(uuid4()), room_id=room.id, deck_title='Deck', mode='collaborative',
                          players={}, host_id=starting_host or host, total=1)
    db.add(session)
    db.flush()
    db.add(RoomQuestion(session_id=session.id, position=0, fingerprint='x',
                        options=[{'id':'a'}] if played else None, failed=not played))
    room.session_id = session.id
    db.flush()
    return room, session


def finish_successfully(client, room_id):
    with write_transaction(client.factory) as db:
        room = db.get(StudyRoom, room_id)
        session = db.get(RoomSession, room.session_id)
        room_study.advance(db, room, session, session.total, utcnow())


def test_hoster_counts_distinct_rooms_once_and_ignores_handoffs_and_failures(client):
    alice, bob = make_user(client, 'alice'), make_user(client, 'bob')
    rooms = []
    with write_transaction(client.factory) as db:
        for _ in range(5):
            rooms.append(hosted_room(db, alice, bob)[0].id)
        handed = hosted_room(db, bob, alice, starting_host=alice)[0].id  # bob only took over later
        empty = hosted_room(db, alice, bob, played=False)[0].id
        left = hosted_room(db, bob, alice, starting_host=alice, keep_host=False)[0].id
        aborted, aborted_session = hosted_room(db, alice, bob)
        room_study.finish(aborted, aborted_session, utcnow())  # unsuccessful finish paths never credit
    for room_id in rooms + [rooms[0], empty, left]:  # replay of rooms[0] does not add progress
        finish_successfully(client, room_id)
    assert row(client, alice, 'hoster').progress == 5 and row(client, alice, 'hoster').unlocked_at is None
    with write_transaction(client.factory) as db:
        replay = RoomSession(id=str(uuid4()), room_id=rooms[0], deck_title='Deck', mode='collaborative',
                             players={}, host_id=alice, total=1)
        db.add(replay)
        db.flush()
        db.add(RoomQuestion(session_id=replay.id, position=0, fingerprint='x', options=[{'id':'a'}]))
        db.get(StudyRoom, rooms[0]).session_id = replay.id
    finish_successfully(client, rooms[0])
    assert row(client, alice, 'hoster').progress == 5
    finish_successfully(client, handed)  # the starting host is credited, the handoff recipient is not
    assert row(client, alice, 'hoster').unlocked_at is not None
    assert row(client, bob, 'hoster') is None
    with client.factory() as db:
        assert db.scalar(select(AchievementCredit.subject).where(AchievementCredit.user_id == alice,
                                                                 AchievementCredit.subject == empty)) is None


# Profile visibility, cleanup, and migration ----------------------------------------------------------

def test_visitors_see_only_unlocked_achievements_without_progress(client):
    owner = client.test_user_id
    for _ in range(10):
        record(client, owner, 'deck_created')
    record(client, owner, 'study_completed')
    owned = client.get('/api/profiles/me').json()
    assert [item['key'] for item in owned['achievements']] == ['deck_master', 'studious', 'hoster']
    assert owned['achievements'][1] | {'progress': 1, 'goal': 10, 'unlocked': False} == owned['achievements'][1]
    username = owned['username']
    make_user(client, 'visitor')
    for browser in (sign_in('visitor'), TestClient(app)):
        public = browser.get(f'/api/profiles/users/{username}').json()['achievements']
        assert public == [{'key':'deck_master', 'name':'Deck Master', 'description':'Create 10 decks.', 'unlocked':True}]
    assert client.patch('/api/profiles/me', json={'visibility':'private'}).status_code == 200
    assert sign_in('visitor').get(f'/api/profiles/users/{username}').status_code == 404
    assert client.get(f'/api/profiles/users/{username}').json()['achievements'][0]['progress'] == 10


def test_account_deletion_removes_achievement_rows(tmp_path, monkeypatch):
    from app import cli
    from app.database import init_database, make_engine
    from sqlalchemy.orm import Session

    engine = make_engine(f"sqlite:///{(tmp_path / 'cli.db').as_posix()}")
    init_database(engine)
    monkeypatch.setattr(cli, 'engine', engine)
    monkeypatch.setattr(cli, 'init_database', lambda: None)
    with Session(engine) as db, db.begin():
        user = create_user(db, 'leaving@example.com', PASSWORD, username='leaving')
        db.flush()
        user_id, uid = user.id, user.uid
        achievements.record(db, user_id, 'deck_created')
        db.add(AchievementCredit(user_id=user_id, achievement_key='hoster', subject='room'))
    assert cli.main(['delete-user', '--uid', uid, '--confirm', uid]) == 0
    with Session(engine) as db:
        assert db.scalar(select(UserAchievement).where(UserAchievement.user_id == user_id)) is None
        assert db.scalar(select(AchievementCredit).where(AchievementCredit.user_id == user_id)) is None
    engine.dispose()


def drop_host_column(engine):
    """Rebuild study_room_sessions as v5 had it; SQLite cannot drop a foreign-key column."""
    import re

    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        cursor.execute('PRAGMA foreign_keys=OFF')
        cursor.execute('PRAGMA legacy_alter_table=ON')
        sql = cursor.execute("SELECT sql FROM sqlite_schema WHERE name = 'study_room_sessions'").fetchone()[0]
        lines = [line for line in sql.splitlines() if 'host_id' not in line]
        sql = re.sub(r',\s*\)\s*$', '\n)', '\n'.join(lines))
        cursor.execute('ALTER TABLE study_room_sessions RENAME TO study_room_sessions_v6')
        cursor.execute(sql)
        cursor.execute('DROP TABLE study_room_sessions_v6')
        raw.commit()
        assert 'host_id' not in {row[1] for row in cursor.execute('PRAGMA table_info(study_room_sessions)')}
    finally:
        raw.close()


def test_v5_migration_backfills_studious_from_completed_sessions_only(tmp_path):
    from sqlalchemy.orm import Session
    from app.database import SCHEMA_VERSION, init_database, make_engine
    from app.models import Deck, StudySession

    engine = make_engine(f"sqlite:///{(tmp_path / 'history.db').as_posix()}")
    init_database(engine)
    day = datetime(2026, 3, 2, 1, 0)  # 09:00 in Manila
    with Session(engine) as db, db.begin():
        busy = create_user(db, 'busy@example.com', PASSWORD, username='busy')
        idle = create_user(db, 'idle@example.com', PASSWORD, username='idle')
        db.flush()
        busy_id, idle_id = busy.id, idle.id
        owned = Deck(title='D', owner_id=busy_id)
        db.add(owned)
        db.flush()
        for index in range(10):
            finished = day + timedelta(minutes=index)
            db.add(StudySession(id=str(uuid4()), owner_id=busy_id, deck_id=owned.id, deck_title='D', total_cards=1,
                                random_seed='s', completed_at=finished,
                                status='completed' if index < 9 else 'exited'))  # exited is not a completion
        db.add(MultipleChoiceSession(id=str(uuid4()), owner_id=busy_id, deck_id=owned.id, deck_title='D',
                                     status='completed', prepare_until=day, expires_at=day,
                                     finished_at=day + timedelta(hours=3)))
        db.add(MultipleChoiceSession(id=str(uuid4()), owner_id=idle_id, deck_id=owned.id, deck_title='D',
                                     status='cancelled', prepare_until=day, expires_at=day, finished_at=day))
    with engine.begin() as connection:  # recreate a v5 file: no achievement tables, no starting host column
        connection.exec_driver_sql('DROP TABLE user_achievements')
        connection.exec_driver_sql('DROP TABLE user_achievement_credits')
        connection.exec_driver_sql('PRAGMA user_version=5')
    drop_host_column(engine)
    init_database(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql('PRAGMA user_version').scalar_one() == SCHEMA_VERSION
        rows = connection.exec_driver_sql(
            'SELECT user_id, achievement_key, progress, period_date, unlocked_at FROM user_achievements').all()
        assert len(rows) == 1  # the idle account's cancelled session is not history
        user_id, key, progress, period, unlocked = rows[0]
        assert (user_id, key, progress, period) == (busy_id, 'studious', 10, '2026-03-02')
        assert unlocked.startswith('2026-03-02 04:00')  # the 10th completion was the Multiple-Choice one
        assert 'host_id' in {row[1] for row in connection.exec_driver_sql('PRAGMA table_info(study_room_sessions)')}
        assert connection.exec_driver_sql('SELECT COUNT(*) FROM study_sessions').scalar_one() == 10
        assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
    assert len(list((tmp_path / '.migration-backups' / 'history.db').glob('pre-migration-*.db'))) == 1
    with engine.begin() as connection:
        connection.exec_driver_sql('PRAGMA user_version=5')
    init_database(engine)  # a repeated upgrade does not count the same history twice
    with engine.connect() as connection:
        assert connection.exec_driver_sql('SELECT COUNT(*), MAX(progress) FROM user_achievements').one() == (1, 10)
    engine.dispose()
