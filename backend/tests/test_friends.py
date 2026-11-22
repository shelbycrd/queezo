from datetime import timedelta

from sqlalchemy import update

from app.auth.service import create_user
from app.models import SessionPresence, utcnow


PASSWORD = 'a disposable test passphrase'


def login(client, username):
    # Each login represents a separate browser. Reusing the previous cookie
    # would revoke that account's session and immediately clear its presence.
    client.cookies.clear()
    response = client.post('/api/auth/login', json={
        'email': f'{username}@example.com', 'password': PASSWORD,
    })
    assert response.status_code == 200
    client.headers['X-CSRF-Token'] = response.json()['csrf_token']


def test_friends_consent_presence_and_profile_privacy(anonymous_client):
    client = anonymous_client
    with client.factory() as db:
        for username in ('alice', 'bob', 'carol'):
            create_user(db, f'{username}@example.com', PASSWORD, username=username)
        db.commit()

    assert client.get('/api/friends').status_code == 401
    login(client, 'alice')
    token = client.headers.pop('X-CSRF-Token')
    assert client.post('/api/friends/requests', json={'username': 'bob'}).status_code == 403
    client.headers['X-CSRF-Token'] = token
    assert client.post('/api/friends/requests', json={'username': 'alice'}).status_code == 422
    for _ in range(2):
        assert client.post('/api/friends/requests', json={'username': 'BOB'}).status_code == 204
    assert len(client.get('/api/friends').json()['outgoing']) == 1
    assert client.get('/api/friends/bob/profile').status_code == 404
    assert client.post('/api/friends/requests/bob/respond', json={'decision': 'accept'}).status_code == 404

    login(client, 'bob')
    assert client.get('/api/friends').json()['incoming'][0]['username'] == 'alice'
    assert client.post('/api/friends/requests', json={'username': 'alice'}).status_code == 409
    assert client.post('/api/friends/requests/alice/respond', json={'decision': 'accept'}).status_code == 204
    assert client.post('/api/friends/presence').status_code == 204
    for visibility in ('public', 'private', 'unlisted'):
        assert client.post('/api/decks', json={'title': f'{visibility} deck', 'visibility': visibility}).status_code == 201

    login(client, 'alice')
    friends = client.get('/api/friends').json()
    assert not friends['incoming'] and not friends['outgoing']
    assert [(friend['username'], friend['online']) for friend in friends['friends']] == [('bob', True)]
    profile = client.get('/api/friends/bob/profile').json()
    assert set(profile) == {'username', 'display_name', 'public_decks'}
    assert [deck['title'] for deck in profile['public_decks']] == ['public deck']
    with client.factory() as db:
        db.execute(update(SessionPresence).values(seen_at=utcnow() - timedelta(minutes=3)))
        db.commit()
    assert client.get('/api/friends').json()['friends'][0]['online'] is False

    login(client, 'carol')
    assert client.get('/api/friends/bob/profile').status_code == 404
    assert client.post('/api/friends/requests', json={'username': 'bob'}).status_code == 204
    login(client, 'bob')
    assert client.post('/api/friends/requests/carol/respond', json={'decision': 'decline'}).status_code == 204
    assert [friend['username'] for friend in client.get('/api/friends').json()['friends']] == ['alice']
    login(client, 'carol')
    response = client.post('/api/friends/requests', json={'username': 'bob'})
    assert response.status_code == 429 and response.headers['retry-after']
