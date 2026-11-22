from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.auth import router as auth
from app.auth.config import get_settings
from app.auth.service import create_user
from app.database import get_db
from app.gwa.main import app as gwa_app
from app.main import app
from app.models import AuthSession, User
from app.services import limits, multiple_choice
from conftest import deck
from test_media_activity import PNG


PASSWORD = 'a disposable phase one password'


def signup_fields():
    return dict(email='phase1@example.com', username='phase_one', display_name='Phase One',
                password=PASSWORD, confirm_password=PASSWORD)


@pytest.mark.parametrize('operation', ['signup', 'login'])
def test_password_work_does_not_block_other_writes(client, monkeypatch, operation):
    entered, release = Event(), Event()
    if operation == 'login':
        original = auth.verify_password
        payload = {'email': 'owner@example.com', 'password': 'correct horse battery staple'}
    else:
        original = auth.hasher.hash
        payload = signup_fields()

    def pause(*args):
        entered.set()
        assert release.wait(10)
        return original(*args)

    if operation == 'login':
        monkeypatch.setattr(auth, 'verify_password', pause)
    else:
        monkeypatch.setattr(auth, 'hasher', SimpleNamespace(hash=pause))

    with ThreadPoolExecutor(max_workers=2) as pool:
        authenticating = pool.submit(client.post, f'/api/auth/{operation}', json=payload)
        try:
            assert entered.wait(5)
            saving = pool.submit(client.post, '/api/decks', json={'title': 'Concurrent save'})
            assert saving.result(timeout=4).status_code == 201
        finally:
            release.set()
        assert authenticating.result(timeout=8).status_code == (200 if operation == 'login' else 201)


def test_credential_is_rechecked_before_session_creation(anonymous_client, monkeypatch):
    client = anonymous_client
    with client.factory.begin() as db:
        identity = create_user(db, 'phase1@example.com', PASSWORD).id
    original = auth.verify_password

    def replace_credential(encoded, password):
        valid = original(encoded, password)
        with client.factory.begin() as db:
            db.get(User, identity).password_hash = auth.hasher.hash('changed disposable password')
        return valid

    monkeypatch.setattr(auth, 'verify_password', replace_credential)
    response = client.post('/api/auth/login', json={'email': 'phase1@example.com', 'password': PASSWORD})
    assert response.status_code == 401 and 'set-cookie' not in response.headers
    with client.factory() as db:
        assert db.scalar(select(AuthSession)) is None


def test_duplicate_signup_is_atomic(anonymous_client):
    client = anonymous_client
    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = [pool.submit(client.post, '/api/auth/signup', json=signup_fields()) for _ in range(2)]
        assert sorted(attempt.result(timeout=12).status_code for attempt in attempts) == [201, 409]
    with client.factory() as db:
        assert len(list(db.scalars(select(User)))) == len(list(db.scalars(select(AuthSession)))) == 1


def test_streamed_request_limits_without_content_length(anonymous_client):
    chunk = b'x' * 9000
    response = anonymous_client.post('/api/auth/signup', content=iter([chunk, chunk]),
                                     headers={'Content-Type': 'application/json'})
    assert response.status_code == 413 and response.headers['cache-control'] == 'no-store'
    with TestClient(gwa_app) as calculator:
        response = calculator.post('/api/gwa/calculate', content=iter([chunk] * 8),
                                   headers={'Content-Type': 'application/json'})
        assert response.status_code == 413


def test_database_errors_are_redacted(anonymous_client, monkeypatch, caplog):
    marker = 'disposable-private-marker'

    def unavailable():
        raise OperationalError('synthetic statement', [marker], Exception(marker))

    monkeypatch.setitem(app.dependency_overrides, get_db, unavailable)
    response = anonymous_client.get('/api/health')
    assert response.status_code == 503
    assert marker not in response.text and marker not in caplog.text
    assert 'Database operation failed' in caplog.text


def test_production_signup_docs_and_unexpected_hosts_are_rejected(anonymous_client, monkeypatch):
    monkeypatch.setenv('AUTH_ENV', 'production')
    monkeypatch.setenv('AUTH_COOKIE_SECURE', 'true')
    monkeypatch.setenv('AUTH_TRUSTED_ORIGINS', 'https://testserver')
    monkeypatch.delenv('AUTH_PUBLIC_SIGNUP', raising=False)
    get_settings.cache_clear()
    with TestClient(app, base_url='https://testserver') as production:
        assert production.post('/api/auth/signup', json=signup_fields()).status_code == 403
        for path in ('/docs', '/redoc', '/openapi.json'):
            assert production.get(path).status_code == 404
        assert production.get('/api/auth/me', headers={'Host': 'unrecognized.example'}).status_code == 400
    with TestClient(gwa_app, base_url='https://testserver') as production:
        for path in ('/gwa/docs', '/gwa/redoc', '/gwa/openapi.json'):
            assert production.get(path).status_code == 404


@pytest.mark.parametrize('original', ['public', 'unlisted'])
def test_share_tokens_are_revoked_for_read_and_copy(client, original):
    record = client.post('/api/decks', json={'title': 'Shared', 'visibility': original}).json()
    path, old = f"/api/decks/{record['id']}", f"/api/shared/decks/{record['share_token']}"
    assert client.get(old).status_code == 200
    if original == 'public':
        assert client.patch(path, json={'visibility': 'unlisted'}).status_code == 200
        assert client.get(old).status_code == 404
        assert client.post(old + '/copy').status_code == 404
    assert client.patch(path, json={'visibility': 'private'}).status_code == 200
    assert client.get(old).status_code == 404
    fresh = client.patch(path, json={'visibility': 'unlisted'}).json()['share_token']
    assert client.get('/api/shared/decks/' + fresh).status_code == 200
    assert client.get(old).status_code == client.post(old + '/copy').status_code == 404


def test_deck_media_copy_and_history_limits_preserve_existing_data(client, monkeypatch):
    monkeypatch.setattr(limits, 'MAX_DECKS', 2)
    monkeypatch.setattr(limits, 'MAX_DECK_MEDIA', len(PNG))
    monkeypatch.setattr(limits, 'MAX_ACCOUNT_MEDIA', len(PNG))
    monkeypatch.setattr(limits, 'MAX_HISTORY_MEDIA', len(PNG))
    identity = deck(client, 0)
    path = f'/api/decks/{identity}'
    payload = {'front': 'Question', 'back': 'Answer', 'front_image': PNG}
    card = client.post(path + '/cards', json=payload).json()
    assert client.post(path + '/cards', json=payload).status_code == 409
    assert client.patch(f"/api/cards/{card['id']}", json={'back_image': PNG}).status_code == 409
    assert client.patch(f"/api/cards/{card['id']}", json={'front': 'Updated'}).status_code == 200
    token = client.patch(path, json={'visibility': 'unlisted'}).json()['share_token']
    assert client.post(f'/api/shared/decks/{token}/copy').status_code == 409
    assert client.post(path + '/study').status_code == 201
    assert client.post(path + '/study').status_code == 409
    assert client.get(path + '/sessions').status_code == 200
    assert client.patch(f"/api/cards/{card['id']}", json={'front_image': None}).status_code == 200
    assert client.post(f'/api/shared/decks/{token}/copy').status_code == 201
    assert client.post('/api/decks', json={'title': 'Extra'}).status_code == 409
    assert client.post(f'/api/shared/decks/{token}/copy').status_code == 409


def test_multiple_choice_admission_limit_releases_on_cancel(client, monkeypatch):
    monkeypatch.setattr(multiple_choice, 'MAX_ACCOUNT_PREPARATIONS', 1)
    identity = deck(client)
    pending, _ = multiple_choice.create_session(identity, client.test_user_id)
    response = client.post(f'/api/decks/{identity}/multiple-choice')
    assert response.status_code == 429 and response.headers['retry-after']
    assert client.post(f"/api/multiple-choice/{pending['id']}/cancel").status_code == 200
    replacement, _ = multiple_choice.create_session(identity, client.test_user_id)
    assert replacement['id'] != pending['id']


def test_copy_rate_limit_is_separate_from_deck_quota(client, monkeypatch):
    monkeypatch.setattr(limits, 'MAX_DECK_COPIES_PER_WINDOW', 1)
    record = client.post('/api/decks', json={'title': 'Shared', 'visibility': 'unlisted'}).json()
    path = f"/api/shared/decks/{record['share_token']}/copy"
    assert client.post(path).status_code == 201
    response = client.post(path)
    assert response.status_code == 429 and int(response.headers['retry-after']) > 0
    assert len(client.get('/api/decks').json()) == 2


def test_friend_lookup_attempts_are_rate_limited(client):
    for number in range(20):
        response = client.post('/api/friends/requests', json={'username': f'missing_{number}'})
        assert response.status_code == 404
    response = client.post('/api/friends/requests', json={'username': 'another_missing'})
    assert response.status_code == 429 and response.headers['retry-after']
