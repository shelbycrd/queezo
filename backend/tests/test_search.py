import pytest

from app.auth.service import create_user
from app.models import Deck, User

PASSWORD = 'a disposable test passphrase'


def add_user(client, name, visibility='public', display_name=None):
    with client.factory.begin() as db:
        user = create_user(db, f'{name}@example.com', PASSWORD, username=name)
        user.profile_visibility = visibility
        if display_name:
            user.display_name = display_name
        return user.id


def login(client, name):
    client.cookies.clear()
    response = client.post('/api/auth/login', json={'email': f'{name}@example.com', 'password': PASSWORD})
    assert response.status_code == 200, response.text
    client.headers['X-CSRF-Token'] = response.json()['csrf_token']


def make_deck(client, title, visibility='private'):
    response = client.post('/api/decks', json={'title': title, 'visibility': visibility})
    assert response.status_code == 201, response.text
    return response.json()


def search(client, q, **params):
    response = client.get('/api/search', params={'q': q, **params})
    assert response.status_code == 200, response.text
    return response.json()


def titles(section):
    return [item['title'] for item in section['items']]


@pytest.fixture
def world(anonymous_client):
    """Alice (searching), Bob (public profile) and Cara (private profile) each own decks of every visibility."""
    client = anonymous_client
    for name, visibility in (('alice', 'public'), ('bob', 'public'), ('cara', 'private')):
        add_user(client, name, visibility, display_name=name.title() + ' Learner')
    decks = {}
    for name in ('bob', 'cara', 'alice'):
        login(client, name)
        for visibility in ('public', 'unlisted', 'private'):
            decks[name, visibility] = make_deck(client, f'Biology {name} {visibility}', visibility)
    login(client, 'alice')
    return client, decks


def test_requires_signed_in_user(anonymous_client):
    assert anonymous_client.get('/api/search', params={'q': 'x'}).status_code == 401
    assert anonymous_client.get('/api/search/recent').status_code == 401


def test_decks_follow_visibility_rules(world):
    client, _ = world
    found = search(client, 'biology')
    # Only other people's public decks, and only my own decks of every visibility.
    assert sorted(titles(found['public_decks'])) == ['Biology bob public', 'Biology cara public']
    assert sorted(titles(found['my_decks'])) == ['Biology alice private', 'Biology alice public', 'Biology alice unlisted']
    everything = repr(found)
    assert 'unlisted' not in repr(found['public_decks']) and 'bob private' not in everything
    assert 'cara unlisted' not in everything and 'cara private' not in everything


def test_public_results_hide_owner_when_profile_not_public(world):
    client, _ = world
    owners = {item['title']: item['owner'] for item in search(client, 'biology', type='public')['public_decks']['items']}
    assert owners['Biology bob public']['username'] == 'bob'
    assert owners['Biology cara public'] is None  # Cara's private profile is not revealed through her public deck.


def test_unpublished_public_deck_is_not_searchable(world):
    client, decks = world
    with client.factory.begin() as db:
        from datetime import datetime
        db.get(Deck, decks['bob', 'public']['id']).unpublished_at = datetime(2026, 1, 1)
    assert 'Biology bob public' not in titles(search(client, 'biology')['public_decks'])


def test_other_accounts_never_see_my_private_decks(world):
    client, _ = world
    login(client, 'bob')
    found = search(client, 'alice')
    assert found['my_decks']['items'] == []
    assert titles(found['public_decks']) == ['Biology alice public']


def test_user_search_is_public_profiles_only(world):
    client, _ = world
    assert [u['username'] for u in search(client, 'learner')['users']['items']] == ['bob']
    assert search(client, 'cara')['users']['items'] == []  # private profile
    assert [u['username'] for u in search(client, 'BOB', type='users')['users']['items']] == ['bob']
    with client.factory.begin() as db:
        from datetime import datetime
        db.query(User).filter_by(username='bob').one().suspended_at = datetime(2026, 1, 1)
    assert search(client, 'bob')['users']['items'] == []
    assert 'email' not in repr(search(client, 'alice', type='users'))


def test_term_is_literal_and_case_insensitive(world):
    client, _ = world
    make_deck(client, '100% sure_thing')
    assert titles(search(client, '100%')['my_decks']) == ['100% sure_thing']
    assert titles(search(client, '%')['my_decks']) == ['100% sure_thing']  # LIKE wildcards are escaped
    assert search(client, '_')['my_decks']['items'][0]['title'] == '100% sure_thing'
    assert search(client, 'sure_th')['my_decks']['items']
    assert search(client, "x' OR '1'='1")['my_decks']['items'] == []
    assert titles(search(client, ' BIOLOGY alice public ', type='mine')['my_decks']) == ['Biology alice public']


def test_blank_and_oversized_queries(world):
    client, _ = world
    blank = search(client, '   ')
    assert blank['query'] == '' and blank['my_decks']['items'] == [] and blank['public_decks']['items'] == []
    assert client.get('/api/search', params={'q': 'x' * 201}).status_code == 422
    assert client.get('/api/search', params={'q': 'x', 'type': 'bogus'}).status_code == 422
    assert client.get('/api/search', params={'q': 'x', 'limit': 31}).status_code == 422
    assert client.get('/api/search', params={'q': 'x', 'page': 0}).status_code == 422
    assert search(client, 'x' * 150)['query'] == 'x' * 80


def test_pagination_and_summary_limit(world):
    client, _ = world
    for number in range(14):
        make_deck(client, f'Chemistry {number:02d}')
    summary = search(client, 'chemistry')
    assert len(summary['my_decks']['items']) == 5 and summary['my_decks']['has_more']
    first = search(client, 'chemistry', type='mine', limit=10)
    second = search(client, 'chemistry', type='mine', limit=10, page=2)
    assert len(first['my_decks']['items']) == 10 and first['my_decks']['has_more']
    assert len(second['my_decks']['items']) == 4 and not second['my_decks']['has_more']
    assert not set(titles(first['my_decks'])) & set(titles(second['my_decks']))
    assert first['public_decks']['items'] == []  # other categories stay empty on a single tab


def test_prefix_matches_rank_first(world):
    client, _ = world
    make_deck(client, 'Intro to Cells')
    make_deck(client, 'Cells and more')
    assert titles(search(client, 'cells', type='mine')['my_decks']) == ['Cells and more', 'Intro to Cells']


def test_recent_resolution_rechecks_visibility(world):
    client, decks = world
    bob_token = decks['bob', 'public']['share_token']
    cara_private = decks['cara', 'private']['id']
    bob_private = decks['bob', 'private']['id']
    mine = decks['alice', 'private']['id']
    refs = [f'shared:{bob_token}', f'deck:{mine}', 'user:bob', 'user:cara', f'deck:{bob_private}',
            f'deck:{cara_private}', 'user:missing', 'garbage', "user:x' OR 1", f'shared:{"a" * 40}', 'user:bob']
    items = client.get('/api/search/recent', params={'ref': refs}).json()['items']
    assert [item['ref'] for item in items] == [f'shared:{bob_token}', f'deck:{mine}', 'user:bob']
    assert [item['path'] for item in items] == [f'/shared/{bob_token}', f'/deck/{mine}', '/u/bob']
    # Becoming private or unpublished hides it again, so stale browser history cannot expose a title.
    login(client, 'bob')
    client.patch(f'/api/decks/{decks["bob", "public"]["id"]}', json={'visibility': 'private'})
    login(client, 'alice')
    assert [item['ref'] for item in client.get('/api/search/recent', params={'ref': refs}).json()['items']] == [
        f'deck:{mine}', 'user:bob']


def test_recent_limits_and_unlisted_deck_by_token(world):
    client, decks = world
    token = decks['bob', 'unlisted']['share_token']
    found = client.get('/api/search/recent', params={'ref': [f'shared:{token}']}).json()['items']
    assert found[0]['visibility'] == 'unlisted'
    many = [f'deck:{decks["alice", "private"]["id"]}'] + [f'user:name_{n}' for n in range(30)]
    assert len(client.get('/api/search/recent', params={'ref': many}).json()['items']) == 1


def test_users_cannot_resolve_each_others_private_refs(world):
    client, decks = world
    login(client, 'bob')
    ref = f'deck:{decks["alice", "private"]["id"]}'
    assert client.get('/api/search/recent', params={'ref': [ref]}).json()['items'] == []
