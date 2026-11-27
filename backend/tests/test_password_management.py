from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import admin_cli
from app.auth.config import get_settings
from app.auth.service import create_user, hasher
from app.main import app
from app.models import AdminAudit, AuthSession, User
from app.services import admin, admin_auth

PASSWORD = 'An-example-password-42!'
REPLACEMENT = 'A-different-password-77?'
OPERATOR_PASSWORD = 'synthetic dedicated operator password'
PARSER = admin_cli.build_parser()


def make_account(client, name='learner'):
    with client.factory.begin() as db:
        return create_user(db, f'{name}@example.com', PASSWORD, username=name).id


def browser(name='learner', password=PASSWORD):
    session = TestClient(app)
    response = session.post('/api/auth/login', json={'email': f'{name}@example.com', 'password': password})
    assert response.status_code == 200, response.text
    session.headers['X-CSRF-Token'] = response.json()['csrf_token']
    return session


def change(session, current=PASSWORD, new=REPLACEMENT, confirm=None):
    return session.post('/api/auth/password', json={
        'current_password': current, 'new_password': new, 'confirm_password': new if confirm is None else confirm})


def sessions_of(client, user_id):
    with client.factory() as db:
        return db.scalar(select(func.count()).select_from(AuthSession).where(AuthSession.user_id == user_id))


def stored_hash(client, user_id):
    with client.factory() as db:
        return db.scalar(select(User.password_hash).where(User.id == user_id))


# User password change ---------------------------------------------------------------------

def test_change_requires_correct_current_password_matching_strong_new_password(anonymous_client):
    user_id = make_account(anonymous_client)
    session = browser()
    original = stored_hash(anonymous_client, user_id)
    cases = [
        (change(session, current='Wrong-password-000'), 'The current password is incorrect.'),
        (change(session, confirm='Something-else-123'), 'Passwords do not match.'),
        (change(session, new='short'), 'Passwords must contain 11–1024 characters.'),
        (change(session, new=PASSWORD), 'Choose a different password.'),
        (session.post('/api/auth/password', json={'new_password': REPLACEMENT}), 'Complete all password fields.'),
    ]
    for response, message in cases:
        assert response.status_code == 422
        assert response.json()['error']['message'] == message
        assert PASSWORD not in response.text and REPLACEMENT not in response.text  # never echoed
    assert stored_hash(anonymous_client, user_id) == original
    assert session.get('/api/auth/me').status_code == 200  # failures keep the session


def test_success_hashes_the_password_and_signs_out_every_session(anonymous_client):
    user_id = make_account(anonymous_client)
    phone, laptop = browser(), browser()
    assert sessions_of(anonymous_client, user_id) == 2
    response = change(laptop)
    assert response.status_code == 200
    assert response.json() == {'message': 'Password changed. Log in again with your new password.'}
    assert get_settings().cookie_name not in laptop.cookies
    assert sessions_of(anonymous_client, user_id) == 0
    for device in (phone, laptop):
        assert device.get('/api/auth/me').status_code == 401
    new_hash = stored_hash(anonymous_client, user_id)
    assert new_hash.startswith('$argon2id$') and hasher.verify(new_hash, REPLACEMENT)
    assert TestClient(app).post('/api/auth/login', json={'email': 'learner@example.com', 'password': PASSWORD}).status_code == 401
    assert browser(password=REPLACEMENT).get('/api/auth/me').status_code == 200


def test_change_requires_authentication_and_csrf(anonymous_client):
    make_account(anonymous_client)
    assert change(TestClient(app)).status_code == 401
    session = browser()
    token = session.headers.pop('X-CSRF-Token')
    assert change(session).status_code == 403
    session.headers['X-CSRF-Token'] = token
    other = TestClient(app, headers={'Origin': 'https://attacker.example'})
    other.cookies = session.cookies
    other.headers['X-CSRF-Token'] = token
    assert change(other).status_code == 403
    assert session.get('/api/auth/me').status_code == 200


def test_incorrect_current_passwords_are_rate_limited(anonymous_client):
    make_account(anonymous_client)
    session = browser()
    for _ in range(5):
        assert change(session, current='Wrong-password-000').status_code == 422
    limited = change(session)  # even the right password waits out the window
    assert limited.status_code == 429 and int(limited.headers['Retry-After']) > 0
    assert limited.json()['error']['message'] == 'Too many password change attempts. Try again later.'
    assert browser().get('/api/auth/me').status_code == 200  # the old password still works


def test_concurrent_changes_apply_only_once(anonymous_client):
    user_id = make_account(anonymous_client)
    sessions = [browser() for _ in range(4)]
    with ThreadPoolExecutor(4) as pool:
        codes = sorted(pool.map(lambda pair: change(pair[1], new=f'{REPLACEMENT}-{pair[0]}').status_code,
                                enumerate(sessions)))
    assert codes.count(200) == 1 and all(code in (401, 409, 429) for code in codes if code != 200)
    current_hash = stored_hash(anonymous_client, user_id)
    winner = next(f'{REPLACEMENT}-{index}' for index in range(4) if _verifies(current_hash, f'{REPLACEMENT}-{index}'))
    assert browser(password=winner).get('/api/auth/me').status_code == 200


def _verifies(encoded, password):
    try:
        return hasher.verify(encoded, password)
    except Exception:
        return False


# Admin CLI reset --------------------------------------------------------------------------

@pytest.fixture
def operator(client):
    admin_auth.set_password(client.factory, 'setup', OPERATOR_PASSWORD, operator='ops_team')
    return admin_auth.authenticate(client.factory, OPERATOR_PASSWORD)


def console(client, operator, lines, prompts=()):
    commands, answers = iter(lines + ['exit']), iter(prompts)
    asked = []

    def prompt(text):
        asked.append(text)
        return next(answers)

    assert admin_cli.shell(client.factory, operator, reader=lambda _: next(commands), prompt=prompt) == 0
    return asked


def audits(client):
    with client.factory() as db:
        return [(row.action, row.target, row.outcome, row.reason) for row in
                db.scalars(select(AdminAudit).where(AdminAudit.action == 'users changepassword').order_by(AdminAudit.id))]


def test_admin_reset_uses_a_hidden_prompt_revokes_sessions_and_audits(client, operator, capsys):
    user_id = make_account(client)
    victim = browser()
    asked = console(client, operator, ['users changepassword learner --reason "Locked out" --yes'],
                    [REPLACEMENT, REPLACEMENT])
    assert asked == ['New password for learner (11–1024 characters): ', 'Confirm new password: ']
    out = capsys.readouterr()
    assert '"password_changed": true' in out.out and '"revoked_sessions": 1' in out.out
    assert REPLACEMENT not in out.out + out.err
    assert victim.get('/api/auth/me').status_code == 401
    assert hasher.verify(stored_hash(client, user_id), REPLACEMENT)
    assert browser(password=REPLACEMENT).get('/api/auth/me').status_code == 200
    assert audits(client) == [('users changepassword', 'learner', 'success', 'Locked out')]
    with client.factory() as db:
        for row in db.scalars(select(AdminAudit)):
            assert REPLACEMENT not in f'{row.action} {row.target} {row.reason} {row.outcome}'


def test_admin_reset_requires_confirmation_and_valid_input(client, operator, capsys):
    user_id = make_account(client)
    original = stored_hash(client, user_id)
    console(client, operator, [
        'users changepassword learner --reason "Reset"',                       # no --yes: rejected by the parser
        'users changepassword learner --reason "Reset" --dry-run',             # preview: no prompt, no change
        'users changepassword learner --reason "Reset" --yes',                 # mismatched confirmation
        'users changepassword learner --reason "Reset" --yes',                 # too short
        'users changepassword nobody_here --reason "Reset" --yes',             # unknown user
    ], ['First-password-1234', 'Second-password-1234', 'short', 'short', REPLACEMENT, REPLACEMENT])
    err = capsys.readouterr().err
    assert 'Invalid command' in err
    assert 'Password confirmation did not match. Nothing was changed.' in err
    assert 'Passwords must contain 11–1024 characters. Nothing was changed.' in err
    assert 'Target not found.' in err
    for secret in ('First-password-1234', 'Second-password-1234', REPLACEMENT):
        assert secret not in err
    assert stored_hash(client, user_id) == original
    assert [row[2] for row in audits(client)] == ['dry-run', 'denied']


def test_inline_password_is_accepted_with_a_warning_and_never_printed(client, operator, capsys):
    user_id = make_account(client)
    console(client, operator, [f'users changepassword learner {REPLACEMENT} --reason "Inline reset" --yes'])
    out = capsys.readouterr()
    assert 'visible on screen' in out.err
    assert REPLACEMENT not in out.out + out.err
    assert hasher.verify(stored_hash(client, user_id), REPLACEMENT)
    assert audits(client) == [('users changepassword', 'learner', 'success', 'Inline reset')]


def test_admin_reset_requires_an_authenticated_operator_and_no_public_route(client, operator):
    make_account(client)
    args = admin_cli.parse_command(PARSER, f'users changepassword learner {REPLACEMENT} --reason "x" --yes')
    with pytest.raises(admin_auth.AdminError, match='authentication expired'):
        admin.execute(client.factory, None, args)
    routes = {getattr(route, 'path', '') for route in app.routes}
    assert not any('changepassword' in path or 'reset' in path for path in routes)
    assert client.post('/api/admin/users/learner/password', json={'password': REPLACEMENT}).status_code in (404, 405)
