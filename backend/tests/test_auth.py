from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.auth.config import get_settings
from app.auth.service import (
    RATE_WINDOW_SECONDS, SESSION_SECONDS, create_user, csrf_token, hash_token, normalize_email,
    reserve_login_attempt, validate_password, verify_password,
)
from app.database import get_db, make_engine
from app.main import app
from app.gwa.main import app as gwa_app
from app.models import AuthSession, Deck, LoginThrottle, StudySession, User, utcnow
from conftest import deck, presentation


PASSWORD = 'An-example-password-42!'


def provision(client, email='learner@example.com', password=PASSWORD):
    with client.factory() as db:
        user = create_user(db, email, password)
        db.commit()
        return user.id


def login(client, email='learner@example.com', password=PASSWORD):
    response = client.post('/api/auth/login', json={'email': email, 'password': password},
                           headers={'Origin': 'http://testserver'})
    assert response.status_code == 200, response.text
    data = response.json()
    client.headers['X-CSRF-Token'] = data['csrf_token']
    return response, data


def test_email_normalization_and_case_insensitive_duplicate_rejection(anonymous_client):
    identity = provision(anonymous_client, '  Learner@EXAMPLE.COM  ')
    with anonymous_client.factory() as db:
        assert db.get(User, identity).email == 'learner@example.com'
        with pytest.raises(ValueError):
            create_user(db, 'LEARNER@example.com', PASSWORD)
        db.rollback()
        assert db.scalar(select(func.count()).select_from(User).where(User.email == 'learner@example.com')) == 1
    assert normalize_email(' Learner@EXAMPLE.com ') == 'learner@example.com'


@pytest.mark.parametrize('email', ['', 'not-an-email', '@example.com', 'a@@example.com', 'a b@example.com'])
def test_invalid_account_emails_are_rejected(anonymous_client, email):
    with anonymous_client.factory() as db, pytest.raises(ValueError):
        create_user(db, email, PASSWORD)


def test_argon2id_password_hash_and_minimum_length(anonymous_client):
    identity = provision(anonymous_client)
    with anonymous_client.factory() as db:
        saved = db.get(User, identity)
        assert saved.password_hash.startswith('$argon2id$')
        assert PASSWORD not in saved.password_hash
        assert verify_password(saved.password_hash, PASSWORD) is True
        assert verify_password(saved.password_hash, 'incorrect-password-42!') is False
    for password in ['', 'x' * 10]:
        with pytest.raises(ValueError):
            validate_password(password)
    validate_password('x' * 11)
    validate_password('x' * 12)


def test_login_me_and_seven_day_hashed_session(anonymous_client):
    identity = provision(anonymous_client)
    response, user = login(anonymous_client, ' LEARNER@EXAMPLE.COM ')
    assert user['id'] == identity
    assert user['email'] == 'learner@example.com'
    token = anonymous_client.cookies.get(get_settings().cookie_name)
    assert token and len(token) >= 40
    assert user['csrf_token'] == csrf_token(token)
    cookie = response.headers['set-cookie'].lower()
    assert 'httponly' in cookie
    assert 'samesite=lax' in cookie or 'samesite=strict' in cookie
    assert f'max-age={SESSION_SECONDS}' in cookie
    assert SESSION_SECONDS == 7 * 24 * 60 * 60
    with anonymous_client.factory() as db:
        session = db.get(AuthSession, hash_token(token))
        assert session is not None
        assert session.user_id == identity
        assert session.token_hash != token
        assert (session.expires_at - session.created_at).total_seconds() == SESSION_SECONDS
        assert token not in repr(session.__dict__)
    me = anonymous_client.get('/api/auth/me')
    assert me.status_code == 200
    assert me.json() == user
    assert 'no-store' in me.headers.get('cache-control', '')


def test_unknown_and_incorrect_passwords_have_identical_errors(anonymous_client):
    provision(anonymous_client)
    wrong = anonymous_client.post('/api/auth/login', json={'email': 'learner@example.com', 'password': 'Wrong-password-123!'})
    unknown = anonymous_client.post('/api/auth/login', json={'email': 'unknown@example.com', 'password': 'Wrong-password-123!'})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert not anonymous_client.cookies.get(get_settings().cookie_name)
    with anonymous_client.factory() as db:
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_logout_revokes_session_and_stolen_cookie_cannot_be_reused(anonymous_client):
    provision(anonymous_client)
    _, user = login(anonymous_client)
    token = anonymous_client.cookies.get(get_settings().cookie_name)
    response = anonymous_client.post('/api/auth/logout')
    assert response.status_code in (200, 204)
    assert anonymous_client.get('/api/auth/me').status_code == 401
    with anonymous_client.factory() as db:
        assert db.get(AuthSession, hash_token(token)) is None
    anonymous_client.cookies.clear()
    anonymous_client.cookies.set(get_settings().cookie_name, token)
    anonymous_client.headers['X-CSRF-Token'] = user['csrf_token']
    assert anonymous_client.get('/api/auth/me').status_code == 401
    assert anonymous_client.post('/api/decks', json={'title': 'Must fail'}).status_code == 401


def test_session_expiration_rejects_me_and_academic_requests(anonymous_client):
    provision(anonymous_client)
    login(anonymous_client)
    token = anonymous_client.cookies.get(get_settings().cookie_name)
    with anonymous_client.factory() as db:
        db.get(AuthSession, hash_token(token)).expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert anonymous_client.get('/api/auth/me').status_code == 401
    assert anonymous_client.get('/api/decks').status_code == 401
    assert anonymous_client.post('/api/decks', json={'title': 'Expired'}).status_code == 401


def test_relogin_rotates_session_and_csrf_secrets(anonymous_client):
    provision(anonymous_client)
    _, first = login(anonymous_client)
    original = anonymous_client.cookies.get(get_settings().cookie_name)
    _, second = login(anonymous_client)
    replacement = anonymous_client.cookies.get(get_settings().cookie_name)
    assert replacement != original
    assert second['csrf_token'] != first['csrf_token']
    with anonymous_client.factory() as db:
        assert db.get(AuthSession, hash_token(original)) is None
        assert db.get(AuthSession, hash_token(replacement)) is not None
    anonymous_client.headers['X-CSRF-Token'] = first['csrf_token']
    assert anonymous_client.post('/api/decks', json={'title': 'Old CSRF'}).status_code == 403
    anonymous_client.headers['X-CSRF-Token'] = second['csrf_token']
    assert anonymous_client.post('/api/decks', json={'title': 'New CSRF'}).status_code == 201


def test_session_survives_new_browser_client_and_new_database_engine(anonymous_client):
    identity = provision(anonymous_client)
    _, user = login(anonymous_client)
    token = anonymous_client.cookies.get(get_settings().cookie_name)
    engine = make_engine(anonymous_client.database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def reopened_db():
        with factory() as db:
            yield db

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = reopened_db
    try:
        with TestClient(app) as refreshed:
            refreshed.cookies.set(get_settings().cookie_name, token)
            response = refreshed.get('/api/auth/me')
            assert response.status_code == 200
            assert response.json()['id'] == identity
            assert response.json()['csrf_token'] == user['csrf_token']
    finally:
        app.dependency_overrides[get_db] = previous
        engine.dispose()


@pytest.mark.parametrize('method,path,payload', [
    ('GET', '/api/dashboard', None), ('GET', '/api/decks', None),
    ('GET', '/api/decks/1', None), ('GET', '/api/decks/1/cards', None),
    ('GET', '/api/cards/1', None), ('GET', '/api/decks/1/sessions', None),
    ('GET', '/api/study/missing', None), ('GET', '/api/study/missing/summary', None),
    ('POST', '/api/decks', {'title': 'Private'}),
    ('POST', '/api/decks/1/cards', {'front': 'Q', 'back': 'A'}),
    ('POST', '/api/decks/1/study', None),
    ('PATCH', '/api/decks/1', {'title': 'Private'}),
    ('PATCH', '/api/cards/1', {'front': 'Q'}),
    ('DELETE', '/api/decks/1', None), ('DELETE', '/api/cards/1', None),
    ('POST', '/api/study/missing/reveal', {'presentation_number': 1, 'presentation_token': 'x' * 36}),
    ('POST', '/api/study/missing/rate', {'presentation_number': 1, 'presentation_token': 'x' * 36, 'difficulty': 'easy'}),
    ('POST', '/api/study/missing/exit', None),
])
def test_unauthenticated_academic_routes_reject_requests(anonymous_client, method, path, payload):
    response = anonymous_client.request(method, path, json=payload)
    assert response.status_code == 401, (method, path, response.text)


def test_csrf_missing_wrong_and_cross_origin_rejected(client):
    me = client.get('/api/auth/me').json()
    client.headers.pop('X-CSRF-Token', None)
    assert client.post('/api/decks', json={'title': 'No CSRF'}).status_code == 403
    assert client.post('/api/auth/logout').status_code == 403
    client.headers['X-CSRF-Token'] = 'incorrect-token'
    assert client.post('/api/decks', json={'title': 'Bad CSRF'}).status_code == 403
    assert client.get('/api/auth/me').status_code == 200
    client.headers['X-CSRF-Token'] = me['csrf_token']
    assert client.post('/api/decks', json={'title': 'Cross site'}, headers={'Origin': 'https://attacker.example'}).status_code == 403
    assert client.post('/api/decks', json={'title': 'Valid CSRF'}, headers={'Origin': 'http://testserver'}).status_code == 201


def test_login_rejects_cross_origin_credentials(anonymous_client):
    provision(anonymous_client)
    response = anonymous_client.post('/api/auth/login', json={'email': 'learner@example.com', 'password': PASSWORD},
                                     headers={'Origin': 'https://attacker.example'})
    assert response.status_code == 403


def test_account_rate_limit_is_persisted_and_returns_retry_after(anonymous_client):
    provision(anonymous_client)
    for _ in range(5):
        response = anonymous_client.post('/api/auth/login', json={'email': 'learner@example.com', 'password': 'Wrong-password-42!'})
        assert response.status_code == 401
    blocked = anonymous_client.post('/api/auth/login', json={'email': 'LEARNER@example.com', 'password': PASSWORD})
    assert blocked.status_code == 429
    assert 0 < int(blocked.headers['retry-after']) <= 900
    with anonymous_client.factory() as db:
        assert db.scalar(select(func.count()).select_from(LoginThrottle)) >= 2


def test_ip_rate_limit_applies_across_different_email_addresses(anonymous_client):
    for number in range(30):
        response = anonymous_client.post('/api/auth/login', json={'email': f'unknown-{number}@example.com', 'password': PASSWORD})
        assert response.status_code == 401, (number, response.text)
    blocked = anonymous_client.post('/api/auth/login', json={'email': 'another-unknown@example.com', 'password': PASSWORD})
    assert blocked.status_code == 429


def test_rate_limit_window_expiration_allows_login_again(anonymous_client):
    provision(anonymous_client)
    for _ in range(5):
        assert anonymous_client.post('/api/auth/login', json={'email': 'learner@example.com', 'password': 'Wrong-password-42!'}).status_code == 401
    assert anonymous_client.post('/api/auth/login', json={'email': 'learner@example.com', 'password': PASSWORD}).status_code == 429
    with anonymous_client.factory() as db:
        for bucket in db.scalars(select(LoginThrottle)):
            bucket.window_started = utcnow() - timedelta(minutes=15, seconds=1)
        db.commit()
    login(anonymous_client)


def test_gwa_requires_authentication_and_session_bound_csrf(client):
    payload = {'courses': [{'units': 3, 'grade': 1.5}]}
    with TestClient(gwa_app) as calculator:
        assert calculator.post('/api/gwa/calculate', json=payload).status_code == 401
        calculator.cookies.update(client.cookies)
        assert calculator.post('/api/gwa/calculate', json=payload).status_code == 403
        calculator.headers['X-CSRF-Token'] = 'incorrect-token'
        assert calculator.post('/api/gwa/calculate', json=payload).status_code == 403
        calculator.headers['X-CSRF-Token'] = client.get('/api/auth/me').json()['csrf_token']
        response = calculator.post('/api/gwa/calculate', json=payload)
        assert response.status_code == 200, response.text
        assert response.json()['gwa'] == 1.5


def test_cross_account_data_isolation_covers_crud_study_and_dashboard(client):
    owner_id = client.get('/api/auth/me').json()['id']
    deck_id = deck(client, 1)
    card_id = client.get(f'/api/decks/{deck_id}/cards').json()[0]['id']
    state = client.post(f'/api/decks/{deck_id}/study').json()
    session_id = state['id']
    provision(client, 'other@example.com')
    with TestClient(app) as other:
        login(other, 'other@example.com')
        assert other.get('/api/decks').json() == []
        assert other.get('/api/dashboard').json() == {'deck_count': 0, 'card_count': 0}
        routes = [
            ('GET', f'/api/decks/{deck_id}', None),
            ('GET', f'/api/decks/{deck_id}/cards', None),
            ('GET', f'/api/decks/{deck_id}/sessions', None),
            ('GET', f'/api/cards/{card_id}', None),
            ('PATCH', f'/api/decks/{deck_id}', {'title': 'Stolen'}),
            ('PATCH', f'/api/cards/{card_id}', {'front': 'Stolen'}),
            ('DELETE', f'/api/decks/{deck_id}', None),
            ('DELETE', f'/api/cards/{card_id}', None),
            ('POST', f'/api/decks/{deck_id}/cards', {'front': 'Stolen', 'back': 'Stolen'}),
            ('POST', f'/api/decks/{deck_id}/study', None),
            ('GET', f'/api/study/{session_id}', None),
            ('GET', f'/api/study/{session_id}/summary', None),
            ('POST', f'/api/study/{session_id}/reveal', presentation(state)),
            ('POST', f'/api/study/{session_id}/rate', {**presentation(state), 'difficulty': 'easy'}),
            ('POST', f'/api/study/{session_id}/exit', None),
        ]
        for method, path, body in routes:
            response = other.request(method, path, json=body)
            assert response.status_code == 404, (method, path, response.text)
        assert other.post('/api/decks', json={'title': 'Other account'}).status_code == 201
    assert client.get(f'/api/decks/{deck_id}').json()['title'] == 'Operating Systems'
    assert client.get('/api/dashboard').json() == {'deck_count': 1, 'card_count': 1}
    with client.factory() as db:
        assert db.get(Deck, deck_id).owner_id == owner_id
        assert db.get(StudySession, session_id).owner_id == owner_id


def test_preexisting_unassigned_decks_remain_inaccessible_to_new_accounts(client):
    with client.factory() as db:
        legacy = Deck(title='Unassigned legacy data', owner_id=None)
        db.add(legacy)
        db.commit()
        identity = legacy.id
    assert client.get('/api/decks').json() == []
    assert client.get('/api/dashboard').json() == {'deck_count': 0, 'card_count': 0}
    assert client.get(f'/api/decks/{identity}').status_code == 404
    assert client.patch(f'/api/decks/{identity}', json={'title': 'Claim'}).status_code == 404
    assert client.delete(f'/api/decks/{identity}').status_code == 404
    with client.factory() as db:
        assert db.get(Deck, identity).title == 'Unassigned legacy data'
        assert db.get(Deck, identity).owner_id is None


def test_production_configuration_defaults_to_secure_host_cookie(monkeypatch):
    monkeypatch.delenv('AUTH_ENV', raising=False)
    monkeypatch.delenv('AUTH_COOKIE_SECURE', raising=False)
    monkeypatch.setenv('AUTH_TRUSTED_ORIGINS', 'https://study.example.com')
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.environment == 'production'
        assert settings.cookie_secure is True
        assert settings.cookie_name.startswith('__Host-')
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize('secure,origins', [
    ('false', 'https://study.example.com'),
    ('true', 'http://study.example.com'),
    ('true', ''), ('true', '*'),
    ('true', 'https://*.example.com'),
    ('true', 'https://study.example.com/private'),
    ('true', 'https://user:password@study.example.com'),
])
def test_production_configuration_rejects_insecure_or_broad_origins(monkeypatch, secure, origins):
    monkeypatch.setenv('AUTH_ENV', 'production')
    monkeypatch.setenv('AUTH_COOKIE_SECURE', secure)
    monkeypatch.setenv('AUTH_TRUSTED_ORIGINS', origins)
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_https_session_cookie_is_secure_host_only_and_not_sent_over_http(anonymous_client, monkeypatch):
    provision(anonymous_client)
    monkeypatch.setenv('AUTH_ENV', 'production')
    monkeypatch.setenv('AUTH_COOKIE_SECURE', 'true')
    monkeypatch.setenv('AUTH_TRUSTED_ORIGINS', 'https://testserver')
    get_settings.cache_clear()
    try:
        with TestClient(app, base_url='https://testserver') as secure:
            response = secure.post('/api/auth/login', json={'email': 'learner@example.com', 'password': PASSWORD},
                                   headers={'Origin': 'https://testserver'})
            assert response.status_code == 200, response.text
            header = response.headers['set-cookie'].lower()
            assert header.startswith('__host-queezo_session=')
            assert '; secure' in header
            assert '; httponly' in header
            assert '; path=/' in header
            assert 'domain=' not in header
            assert secure.get('/api/auth/me').status_code == 200
            assert secure.get('http://testserver/api/auth/me').status_code == 401
    finally:
        get_settings.cache_clear()


def test_login_attempt_prunes_expired_buckets_but_retains_live_metadata(anonymous_client, monkeypatch):
    now = utcnow()
    monkeypatch.setattr('app.auth.service.utcnow', lambda: now)
    expired_keys = [f'ip:{hash_token("old-address")}', f'email:{hash_token("old@example.com")}']
    fresh_key = f'email:{hash_token("fresh@example.com")}'
    with anonymous_client.factory() as db:
        db.add_all([
            LoginThrottle(key=expired_keys[0], window_started=now - timedelta(seconds=RATE_WINDOW_SECONDS), attempts=30),
            LoginThrottle(key=expired_keys[1], window_started=now - timedelta(seconds=RATE_WINDOW_SECONDS + 1), attempts=5),
            LoginThrottle(key=fresh_key, window_started=now - timedelta(seconds=RATE_WINDOW_SECONDS - 1), attempts=3),
        ])
        db.commit()
        assert reserve_login_attempt(db, 'new@example.com', 'new-address') == 0
        db.flush()
        db.commit()
    with anonymous_client.factory() as db:
        buckets = {bucket.key: bucket for bucket in db.scalars(select(LoginThrottle))}
        assert set(buckets) == {fresh_key, f'ip:{hash_token("new-address")}', f'email:{hash_token("new@example.com")}'}
        assert all(key not in buckets for key in expired_keys)
        assert buckets[fresh_key].attempts == 3
        assert buckets[fresh_key].window_started == now - timedelta(seconds=RATE_WINDOW_SECONDS - 1)
        assert buckets[f'ip:{hash_token("new-address")}'].attempts == 1
        assert buckets[f'email:{hash_token("new@example.com")}'].attempts == 1


def test_blocked_ip_random_emails_do_not_grow_throttle_metadata(anonymous_client, monkeypatch):
    now = utcnow()
    monkeypatch.setattr('app.auth.service.utcnow', lambda: now)
    address = 'blocked-address'
    ip_key = f'ip:{hash_token(address)}'
    existing_email_key = f'email:{hash_token("existing@example.com")}'
    with anonymous_client.factory() as db:
        db.add_all([
            LoginThrottle(key=ip_key, window_started=now, attempts=30),
            LoginThrottle(key=existing_email_key, window_started=now, attempts=3),
        ])
        db.commit()
        for number in range(50):
            retry = reserve_login_attempt(db, f'random-{number}@example.com', address)
            assert retry == RATE_WINDOW_SECONDS
            db.flush()
            db.commit()
    with anonymous_client.factory() as db:
        buckets = {bucket.key: bucket.attempts for bucket in db.scalars(select(LoginThrottle))}
        assert buckets == {ip_key: 30, existing_email_key: 3}


def test_password_change_checks_current_password_and_rotates_sessions(anonymous_client):
    client = anonymous_client
    provision(client)
    cookie_name = get_settings().cookie_name
    login(client)
    previous = client.cookies[cookie_name]
    client.cookies.clear()
    _, account = login(client)
    original = client.cookies[cookie_name]
    assert account['email_verified'] is False
    replacement = 'Different-test-password-51!'
    body = {'current_password': PASSWORD, 'new_password': replacement, 'confirm_password': replacement}
    token = client.headers.pop('X-CSRF-Token')
    assert client.post('/api/auth/password', json=body).status_code == 403
    client.headers['X-CSRF-Token'] = token
    assert client.post('/api/auth/password', json={**body, 'current_password': 'Incorrect'}).status_code == 422
    assert client.post('/api/auth/password', json={**body, 'confirm_password': 'Mismatch'}).status_code == 422
    changed = client.post('/api/auth/password', json=body)
    assert changed.status_code == 200
    current = client.cookies[cookie_name]
    assert current not in {original, previous}
    assert client.get('/api/auth/me').json()['csrf_token'] == changed.json()['csrf_token']

    for revoked in (original, previous):
        client.cookies.clear()
        client.cookies.set(cookie_name, revoked)
        assert client.get('/api/auth/me').status_code == 401
    client.cookies.clear()
    assert client.post('/api/auth/login', json={'email':'learner@example.com','password':PASSWORD}).status_code == 401
    login(client, password=replacement)
