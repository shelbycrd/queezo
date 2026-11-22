import json
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import cli
from app.database import init_database, make_engine
from app.models import User, Deck
from app.auth.service import create_user
from conftest import deck


def fields(**overrides):
    result = dict(display_name='Study Friend', username='study_friend', email='friend@example.com',
                  password='QuietCloud!73Maple', confirm_password='QuietCloud!73Maple')
    result.update(overrides)
    return result


def test_signup_creates_identity_and_cookie_session_without_password_exposure(anonymous_client):
    response = anonymous_client.post('/api/auth/signup', json=fields(), headers={'Origin':'http://testserver'})
    assert response.status_code == 201, response.text
    user = response.json()
    assert str(UUID(user['uid'])) == user['uid']
    assert user['username'] == 'study_friend'
    assert user['display_name'] == 'Study Friend'
    assert anonymous_client.get('/api/auth/me').json() == user
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'QuietCloud' not in response.text
    with anonymous_client.factory() as db:
        assert db.get(User,user['id']).password_hash.startswith('$argon2id$')


def test_signup_uniqueness_is_case_insensitive_but_display_names_can_repeat(anonymous_client):
    first = anonymous_client.post('/api/auth/signup', json=fields()).json()
    assert anonymous_client.post('/api/auth/signup',json=fields(username='other_user',email=' FRIEND@example.COM ')).status_code == 409
    assert anonymous_client.post('/api/auth/signup',json=fields(username='STUDY_FRIEND',email='other@example.com')).status_code == 409
    response = anonymous_client.post('/api/auth/signup',json=fields(username='other_user',email='other@example.com'))
    assert response.status_code == 201
    assert response.json()['display_name'] == first['display_name']
    assert response.json()['uid'] != first['uid']
    assert anonymous_client.get('/api/decks').json() == []


@pytest.mark.parametrize('change', [dict(display_name=''),dict(username='a'),dict(username='has spaces'),dict(email='invalid'),
    dict(password='short',confirm_password='short'),dict(confirm_password='Different'),dict(password=None),dict(username=None),dict(display_name=None),dict(uid='injected')])
def test_invalid_signup_is_rejected_without_secret_echo(anonymous_client,change):
    response = anonymous_client.post('/api/auth/signup',json=fields(**change))
    assert response.status_code == 422
    assert 'QuietCloud!73Maple' not in response.text
    with anonymous_client.factory() as db:
        assert db.scalar(select(User)) is None


def test_strength_advice_does_not_block_valid_eleven_character_password(anonymous_client):
    assert anonymous_client.post('/api/auth/signup',json=fields(password='a'*11,confirm_password='a'*11)).status_code == 201


def test_signup_origin_content_type_size_and_rate_limit(anonymous_client):
    assert anonymous_client.post('/api/auth/signup',json=fields(),headers={'Origin':'https://evil.example'}).status_code == 403
    assert anonymous_client.post('/api/auth/signup',data={'email':'friend@example.com'}).status_code == 422
    assert anonymous_client.post('/api/auth/signup',content='x'*17000,headers={'Content-Type':'application/json'}).status_code == 422
    for _ in range(8):
        assert anonymous_client.post('/api/auth/signup',json={}).status_code == 422
    response = anonymous_client.post('/api/auth/signup',json=fields())
    assert response.status_code == 429
    assert int(response.headers['retry-after']) > 0


def test_cli_inventory_delete_confirmation_and_revoked_sessions(client,monkeypatch,capsys):
    deck_id = deck(client)
    assert client.post(f'/api/decks/{deck_id}/study').status_code == 201
    user = client.get('/api/auth/me').json()
    with client.factory() as db:
        target = db.get_bind()
    monkeypatch.setattr(cli,'engine',target)
    monkeypatch.setattr(cli,'init_database',lambda:None)
    assert cli.main(['list-users']) == 0
    output = capsys.readouterr().out
    assert user['uid'] in output and 'password_hash' not in output and '$argon' not in output
    assert cli.main(['show-user','--uid',user['uid']]) == 0
    assert json.loads(capsys.readouterr().out)['deck_count'] == 1
    assert cli.main(['delete-user','--uid',user['uid'],'--confirm','wrong']) == 1
    assert client.get(f'/api/decks/{deck_id}').status_code == 200
    assert cli.main(['delete-user','--uid',user['uid'],'--confirm',user['uid']]) == 0
    assert client.get('/api/auth/me').status_code == 401
    with client.factory() as db:
        for table in ('users','decks','flashcards','study_sessions','study_session_cards','auth_sessions'):
            assert db.execute(text('SELECT count(*) FROM '+table)).scalar_one() == 0


def test_cli_revoke_and_delete_preserve_other_accounts_and_their_decks(client,monkeypatch,capsys):
    preserved_deck = deck(client)
    user = client.get('/api/auth/me').json()
    with client.factory() as db:
        target = db.get_bind()
        other = create_user(db,'other@example.com','Another safe test password')
        other_uid = other.uid
        db.add(Deck(owner_id=other.id,title='Other private deck'))
        db.commit()
    monkeypatch.setattr(cli,'engine',target)
    monkeypatch.setattr(cli,'init_database',lambda:None)
    assert cli.main(['delete-user','--uid',other_uid,'--confirm',other_uid]) == 0
    assert client.get(f'/api/decks/{preserved_deck}').status_code == 200
    assert cli.main(['revoke-sessions','--uid',user['uid']]) == 0
    assert client.get('/api/auth/me').status_code == 401
    with client.factory() as db:
        assert db.get(Deck,preserved_deck) is not None
        assert db.get(User,user['id']) is not None


def test_profile_migration_backfills_once_and_preserves_legacy_password_and_ids(tmp_path):
    engine = make_engine(f'sqlite:///{tmp_path / "old.db"}')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at DATETIME NOT NULL)'))
        db.execute(text("INSERT INTO users VALUES(1,'original@example.com','unchanged-hash','2026-01-01 00:00:00')"))
    init_database(engine)
    with Session(engine) as db:
        user = db.get(User,1)
        uid = user.uid
        assert user.password_hash == 'unchanged-hash'
        assert user.username == 'user_1'
        assert (user.profile_visibility, user.avatar, user.bio, user.interest_tags) == ('unlisted', 'cat', '', [])
        assert user.display_name_changed_at is None and user.featured_deck_id is None
    init_database(engine)
    with Session(engine) as db:
        assert db.get(User,1).uid == uid
    engine.dispose()
