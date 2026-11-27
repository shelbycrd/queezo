from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

from app import admin_cli, cli
from app.auth.service import create_user, hash_token, hasher
from app.database import SCHEMA_VERSION, init_database, make_engine
from app.models import (
    AdminCredential, AuthSession, Deck, MultipleChoiceSession, ProfileReport, RoomInvite, RoomMember, RoomQuestion,
    RoomSession, StudyRoom, StudySession, User, utcnow,
)
from app.services import admin, admin_auth
from app.sqlite_ops import publish_success


PASSWORD = 'synthetic dedicated operator password'
REPLACEMENT = 'synthetic replacement operator password'
TRUSTED = {'Origin': 'http://testserver'}
PARSER = admin_cli.build_parser()


@pytest.fixture
def operator(client):
    admin_auth.set_password(client.factory, 'setup', PASSWORD, operator='ops_team')
    return admin_auth.authenticate(client.factory, PASSWORD)


def run(client, operator, line):
    return admin.execute(client.factory, operator, admin_cli.parse_command(PARSER, line))


def test_dedicated_hash_attempt_limits_and_rotation(client):
    factory = client.factory
    with pytest.raises(admin_auth.AdminError, match='not configured'):
        admin_auth.authenticate(factory, PASSWORD)
    admin_auth.set_password(factory, 'setup', PASSWORD, operator='ops_team')
    original = admin_auth.current_credential(factory)
    assert original.password_hash.startswith('$argon2id$')
    assert hasher.verify(original.password_hash, PASSWORD)
    assert original.password_hash != PASSWORD
    with pytest.raises(admin_auth.AdminError, match='already configured'):
        admin_auth.set_password(factory, 'setup', PASSWORD, operator='another')
    for _ in range(5):
        with pytest.raises(admin_auth.AdminError, match='authentication failed'):
            admin_auth.authenticate(factory, 'correct horse battery staple')
    with pytest.raises(admin_auth.AdminError, match='Too many'):
        admin_auth.authenticate(factory, PASSWORD)
    admin_auth.set_password(factory, 'recover', REPLACEMENT, expected=original, reason='Lost credential')
    with pytest.raises(admin_auth.AdminError, match='authentication failed'):
        admin_auth.authenticate(factory, PASSWORD)
    principal = admin_auth.authenticate(factory, REPLACEMENT)
    assert principal.operator == 'ops_team'
    with pytest.raises(admin_auth.AdminError, match='credential changed'):
        admin_auth.set_password(factory, 'recover', 'synthetic third password', expected=original, reason='Stale request')
    admin_auth.set_password(factory, 'rotate', PASSWORD, principal=principal,
                            expected=admin_auth.current_credential(factory))
    with pytest.raises(admin_auth.AdminError, match='authentication expired'):
        run(client, principal, 'system status')
    latest = admin_auth.authenticate(factory, PASSWORD)
    assert latest.revision == 3
    events = run(client, latest, 'audit list --limit 100')
    recovered = next(row for row in events if row['action'] == 'auth recover')
    assert (recovered['operator'], recovered['reason']) == ('server-root', 'Lost credential')
    assert sum(row['action'] == 'auth login' and row['outcome'] == 'denied' for row in events) == 6
    assert PASSWORD not in str(events) and REPLACEMENT not in str(events)


def test_users_list_includes_email_and_verification_status(client, operator):
    current = client.get('/api/auth/me').json()
    [user] = run(client, operator, 'users list')
    assert user['username'] == current['username']
    assert user['email'] == 'owner@example.com'
    assert user['email_verified'] is current['email_verified'] is False
    assert 'password_hash' not in user
    assert 'email' not in run(client, operator, f"users inspect {user['username']}")


def test_parser_restricts_commands_and_values(client, operator):
    for line in ('shell ls', 'users suspend owner --yes', 'users suspend owner --reason testing',
                 'users suspend owner --reason testing --yes --dry-run', 'rooms inspect abc',
                 'decks inspect 9223372036854775808', 'audit list --limit 101',
                 'users list; ls', 'users list --off 0', 'users search "unbalanced'):
        with pytest.raises(admin_auth.AdminError, match='Invalid command'):
            run(client, operator, line)
    with pytest.raises(admin_auth.AdminError, match='printable reason'):
        run(client, operator, 'users suspend owner --reason "   " --yes')
    with pytest.raises(admin_auth.AdminError, match='authentication expired'):
        run(client, None, 'users list')


def test_interactive_commands_and_inactivity(client, operator, capsys):
    lines = iter(['whoami', 'help', 'system status', 'clear', 'invalid_command', 'exit'])
    assert admin_cli.shell(client.factory, operator, reader=lambda _: next(lines)) == 0
    out = capsys.readouterr()
    assert 'ops_team' in out.out and 'users suspend' in out.out and '"schema_version":' in out.out
    assert '\033[2J' in out.out and 'Invalid command' in out.err

    def idle(remaining):
        assert 0 < remaining <= admin_cli.IDLE_SECONDS
        raise TimeoutError

    assert admin_cli.shell(client.factory, operator, reader=idle) == 0
    assert 'inactivity' in capsys.readouterr().out


def test_cli_refuses_noninteractive_login_and_nonroot_recovery(client, monkeypatch, capsys):
    monkeypatch.setattr(admin_cli.sys.stdin, 'isatty', lambda: False)
    assert cli.main(['admin']) == 1
    assert 'interactive Docker terminal' in capsys.readouterr().err
    monkeypatch.setattr(admin_cli, 'terminal_required', lambda: None)
    monkeypatch.setattr(admin_cli.os, 'geteuid', lambda: 10001, raising=False)
    assert cli.main(['admin', 'recover', '--yes', '--reason', 'Lost credential']) == 1
    assert 'server operator' in capsys.readouterr().err


def test_suspension_and_revocation_close_http_and_live_sessions(client, operator):
    username = client.get('/api/auth/me').json()['username']
    with client.factory.begin() as db:
        room_id = str(uuid4())
        db.add(StudyRoom(id=room_id, host_id=client.test_user_id))
        db.flush()
        db.add(RoomMember(room_id=room_id, user_id=client.test_user_id, seen_at=utcnow()))
    preview = run(client, operator, f'users suspend {username} --reason "Verify account" --dry-run')
    assert preview['mode'] == 'dry-run' and preview['revoked_sessions'] == 1
    assert client.get('/api/auth/me').status_code == 200
    with client.websocket_connect('/api/rooms/notifications/live', headers=TRUSTED) as notices:
        notices.receive_json()
        with client.websocket_connect(f'/api/rooms/{room_id}/live', headers=TRUSTED) as room:
            room.receive_json()
            result = run(client, operator, f'users suspend {username} --reason "Verify account" --yes')
            assert result['revoked_sessions'] == 1 and result['suspended']
            with pytest.raises(WebSocketDisconnect) as closed:
                room.receive_json()
            assert closed.value.code == 1008
        with pytest.raises(WebSocketDisconnect) as closed:
            notices.receive_json()
        assert closed.value.code == 1008
    assert client.get('/api/auth/me').status_code == 401
    login = {'email': 'owner@example.com', 'password': 'correct horse battery staple'}
    assert client.post('/api/auth/login', json=login).status_code == 401
    with pytest.raises(admin_auth.AdminError, match='already suspended'):
        run(client, operator, f'users suspend {username} --reason Duplicate --yes')
    run(client, operator, f'users unsuspend {username} --reason Verified --yes')
    assert client.get('/api/auth/me').status_code == 401
    assert client.post('/api/auth/login', json=login).status_code == 200
    assert run(client, operator, f'users revoke-sessions {username} --reason Logout --yes')['revoked_sessions'] == 1
    assert client.get('/api/auth/me').status_code == 401
    events = run(client, operator, 'audit list')
    assert {row['outcome'] for row in events if row['action'] == 'users suspend'} == {'success', 'dry-run', 'denied'}
    assert run(client, operator, f"audit inspect {events[0]['id']}") == events[0]


def test_concurrent_suspensions_have_one_committed_change(client, operator):
    username = client.get('/api/auth/me').json()['username']

    def suspend():
        try:
            return run(client, operator, f'users suspend {username} --reason Concurrent --yes')['mode']
        except admin_auth.AdminError as error:
            assert 'already suspended' in str(error)
            return 'denied'

    with ThreadPoolExecutor(max_workers=2) as workers:
        attempts = [workers.submit(suspend) for _ in range(2)]
        assert sorted(attempt.result() for attempt in attempts) == ['denied', 'success']
    assert client.get('/api/auth/me').status_code == 401


def test_moderation_rolls_back_when_audit_write_fails(client, operator):
    username = client.get('/api/auth/me').json()['username']
    with client.factory.begin() as db:
        db.execute(text("""
            CREATE TRIGGER reject_audit BEFORE INSERT ON admin_audit
            WHEN NEW.action = 'users suspend'
            BEGIN SELECT RAISE(ABORT, 'synthetic audit failure'); END
        """))
    with pytest.raises(IntegrityError):
        run(client, operator, f'users suspend {username} --reason Test --yes')
    assert client.get('/api/auth/me').status_code == 200
    with client.factory() as db:
        assert db.get(User, client.test_user_id).suspended_at is None
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 1


def test_deck_restore_preserves_history_and_replaces_share_link(client, operator):
    owner = client.test_user_id
    created = client.post('/api/decks', json={'title': 'Public test', 'visibility': 'public'}).json()
    deck_id, token = created['id'], created['share_token']
    assert client.post(f'/api/decks/{deck_id}/cards', json={'front': 'Question', 'back': 'Answer'}).status_code == 201
    classic = client.post(f'/api/decks/{deck_id}/study')
    assert classic.status_code == 201
    previous_session = classic.json()['id']
    shared_id = str(uuid4())
    now = utcnow()
    with client.factory.begin() as db:
        db.add(MultipleChoiceSession(id=shared_id, owner_id=owner, deck_id=deck_id, deck_title='Public test',
                                     shared_access=hash_token(token), prepare_until=now + timedelta(minutes=1),
                                     expires_at=now + timedelta(hours=1)))
    assert client.get(f'/api/multiple-choice/{shared_id}').status_code == 200
    other_token = client.post('/api/decks', json={'title': 'Another', 'visibility': 'public'}).json()['share_token']
    assert client.get(f'/api/shared/decks/{token}').status_code == 200
    run(client, operator, f'decks unpublish {deck_id} --reason "Policy review" --yes')
    assert client.get(f'/api/shared/decks/{token}').status_code == 404
    assert client.get(f'/api/multiple-choice/{shared_id}').status_code == 404
    assert client.get(f'/api/shared/decks/{other_token}').status_code == 200
    response = client.patch(f'/api/decks/{deck_id}', json={'visibility': 'public', 'title': 'Edited'})
    assert response.status_code == 200 and response.json()['share_token'] is None
    assert client.patch(f'/api/decks/{deck_id}', json={'visibility': 'unlisted'}).status_code == 409
    assert client.get(f'/api/study/{previous_session}').status_code == 200
    run(client, operator, f'decks restore {deck_id} --reason Cleared --yes')
    assert client.get(f'/api/shared/decks/{token}').status_code == 404
    assert client.get(f'/api/multiple-choice/{shared_id}').status_code == 404
    current = client.get(f'/api/decks/{deck_id}').json()
    assert current['share_token'] != token and current['visibility'] == 'public'
    assert client.get('/api/shared/decks/' + current['share_token']).status_code == 200
    with client.factory() as db:
        assert db.get(Deck, deck_id).owner_id == owner
        assert db.get(StudySession, previous_session)
    assert run(client, operator, f'decks inspect {deck_id}')['cards'] == 1


def test_rooms_close_preserves_scoring_notifies_member_and_invalidates_invites(client, operator):
    owner = client.test_user_id
    room_id, session_id = str(uuid4()), str(uuid4())
    with client.factory.begin() as db:
        invitee = create_user(db, 'other@example.com', 'synthetic test password', username='invitee')
        deck = Deck(owner_id=owner, title='Synthetic', visibility='public')
        db.add(deck)
        db.flush()
        db.add(StudyRoom(id=room_id, host_id=owner, phase='reveal', session_id=session_id,
                         deck_id=deck.id, deck_owner_id=owner))
        db.flush()
        db.add(RoomMember(room_id=room_id, user_id=owner, seen_at=utcnow()))
        db.add(RoomInvite(room_id=room_id, user_id=invitee.id, sender_id=owner))
        db.add(RoomSession(id=session_id, room_id=room_id, deck_title='Synthetic', mode='challenge', total=1,
                           players={str(owner): {'username': 'host'}}, scores={str(owner): {'score': 850}}))
        db.flush()
        db.add(RoomQuestion(session_id=session_id, position=0, fingerprint='test', front='Question',
                            options=[{'id': 'test', 'text': 'Answer'}], correct_id='test'))
    with client.websocket_connect(f'/api/rooms/{room_id}/live', headers=TRUSTED) as socket:
        socket.receive_json()
        run(client, operator, f'rooms close {room_id} --reason Moderated --yes')
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()
    response = client.get(f'/api/rooms/{room_id}')
    assert response.status_code == 404 and 'closed' in response.json()['error']['message']
    view = run(client, operator, f'rooms inspect {room_id}')
    assert view['phase'] == 'closed' and view['pending_invites'] == 0
    assert view['result']['standings'][0]['score'] == 850
    with pytest.raises(admin_auth.AdminError, match='already closed'):
        run(client, operator, f'rooms close {room_id} --reason Duplicate --yes')


def test_reports_queries_and_diagnostics(client, operator, tmp_path, monkeypatch):
    with client.factory.begin() as db:
        other = create_user(db, 'reporter@example.com', 'synthetic test password', username='learner')
        one = ProfileReport(target_id=client.test_user_id, reporter_id=other.id,
                            reason='spam', explanation='Synthetic report')
        two = ProfileReport(target_id=client.test_user_id, reporter_id=other.id, reason='other')
        db.add_all([one, two])
        db.flush()
        first, second = one.id, two.id
    assert run(client, operator, 'users search LEARN')[0]['username'] == 'learner'
    assert not run(client, operator, 'users search "%"')
    assert run(client, operator, 'reports list --limit 1')[0]['id'] == second
    assert run(client, operator, f'reports inspect {first}')['explanation'] == 'Synthetic report'
    assert run(client, operator, f'reports resolve {first} --reason Reviewed --yes')['status'] == 'resolved'
    assert run(client, operator, f'reports dismiss {second} --reason Reviewed --yes')['status'] == 'dismissed'
    with pytest.raises(admin_auth.AdminError, match='final disposition'):
        run(client, operator, f'reports resolve {second} --reason Reviewed --yes')
    assert run(client, operator, 'system stats')['pending_reports'] == 0
    assert run(client, operator, 'system database')['foreign_keys']
    assert 'daily_status' in run(client, operator, 'system backups')
    marker = tmp_path / '.last-success'
    publish_success(marker, date(2026, 11, 25))
    with client.factory() as db:
        assert admin.backup_info(db, marker)['daily_last_success_utc'] == '2026-11-25'
    def fake_get(self, url):
        return httpx.Response(200, request=httpx.Request('GET', url), json={
            'models': [{'name': 'test-model:latest'}, {'name': 'irrelevant-model'}],
        })
    monkeypatch.setenv('OLLAMA_MODEL', 'test-model:latest')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    monkeypatch.setattr(httpx.Client, 'get', fake_get)
    assert run(client, operator, 'ai status') == {
        'configured_model': 'test-model:latest', 'reachable': True, 'configured_model_installed': True,
    }
    assert run(client, operator, 'ai stats')['solo_sessions'] == 0
    assert run(client, operator, 'ai cache-stats')['ollama_only'] == 0


def test_v3_migration_adds_nullable_fields_and_keeps_existing_rows(tmp_path):
    database = tmp_path / 'old.db'
    engine = make_engine(f'sqlite:///{database.as_posix()}')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)')
        connection.exec_driver_sql('CREATE TABLE decks (id INTEGER PRIMARY KEY, owner_id INTEGER, visibility TEXT)')
        connection.exec_driver_sql('CREATE TABLE profile_reports (id INTEGER PRIMARY KEY, reviewed_at DATETIME)')
        connection.exec_driver_sql("INSERT INTO users VALUES (1, 'existing')")
        connection.exec_driver_sql("INSERT INTO decks VALUES (2, 1, 'unlisted')")
        connection.exec_driver_sql('INSERT INTO profile_reports VALUES (3, NULL)')
        connection.exec_driver_sql('PRAGMA user_version=3')
    init_database(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql('PRAGMA user_version').scalar_one() == SCHEMA_VERSION
        assert connection.exec_driver_sql('SELECT username, suspended_at FROM users').one() == ('existing', None)
        assert connection.exec_driver_sql('SELECT owner_id, visibility, unpublished_at FROM decks').one() == (1, 'unlisted', None)
        assert connection.exec_driver_sql('SELECT id, disposition FROM profile_reports').one() == (3, None)
        assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
    assert len(list((tmp_path / '.migration-backups' / database.name).glob('pre-migration-*.db'))) == 1
    with sessionmaker(bind=engine)() as db:
        assert db.get(AdminCredential, 1) is None
    engine.dispose()
