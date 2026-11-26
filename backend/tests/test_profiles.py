from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app import cli
from app.auth.service import create_user
from app.models import Friendship, ProfileAvatarChange, ProfileReport, User
from app.routers import profiles


def patch(client, **updates):
    profile = client.get('/api/profiles/me').json()
    body = {key: profile[key] for key in (
        'display_name', 'bio', 'interest_tags', 'avatar', 'visibility', 'featured_deck_id',
    )}
    return client.patch('/api/profiles/me', json={**body, **updates})


def public_path(client):
    return '/api/profiles/users/' + client.get('/api/profiles/me').json()['username']


def make_deck(client, title, visibility):
    response = client.post('/api/decks', json={'title': title, 'visibility': visibility})
    assert response.status_code == 201, response.text
    return response.json()


def add_user(client, name, visibility='unlisted'):
    with client.factory.begin() as db:
        user = create_user(db, f'{name}@example.com', 'correct horse battery staple', username=name)
        user.profile_visibility = visibility
        return user.id


def test_profile_privacy_controls_search_and_public_payload(client):
    path = public_path(client)
    assert patch(client, bio='<script>text stays plain</script>', interest_tags=['Science']).status_code == 200
    visible = make_deck(client, 'Visible', 'public')
    make_deck(client, 'Hidden', 'private')
    make_deck(client, 'Link only', 'unlisted')
    cookies = dict(client.cookies.items())
    client.cookies.clear()
    public = client.get(path)
    assert public.status_code == 200
    assert set(public.json()) == {'username', 'display_name', 'joined_at', 'bio', 'interest_tags', 'avatar',
                                  'is_owner', 'featured_deck', 'achievements'}
    assert public.json()['achievements'] == []  # visitors never receive locked progress
    assert not public.json()['is_owner']
    assert public.json()['bio'] == '<script>text stays plain</script>'
    assert public.headers['Cache-Control'] == 'no-store'
    assert client.get('/api/profiles/search').json() == []
    assert client.get('/api/profiles/me').status_code == 401
    assert [d['title'] for d in client.get(path + '/decks').json()['items']] == ['Visible']
    assert client.get('/api/profiles/users/missing').status_code == 404
    client.cookies.update(cookies)
    assert patch(client, visibility='public').status_code == 200
    assert [row['username'] for row in client.get('/api/profiles/search?q=OWNER').json()] == [path.rsplit('/', 1)[-1]]
    assert patch(client, visibility='private').status_code == 200
    assert client.get(path).json()['is_owner']
    assert client.get('/api/community/decks').json()[0]['share_token'] == visible['share_token']
    peer = add_user(client, 'visitor')
    with client.factory.begin() as db:
        first, second = sorted([client.test_user_id, peer])
        db.add(Friendship(first_id=first, second_id=second, requester_id=first, accepted=True))
    auth = client.post('/api/auth/login', json={'email':'visitor@example.com', 'password':'correct horse battery staple'})
    assert auth.status_code == 200
    assert client.get(path).status_code == 404
    assert client.get(path + '/decks').status_code == 404
    assert client.get('/api/friends/' + path.rsplit('/', 1)[-1] + '/profile').status_code == 404
    assert client.get('/api/profiles/search?q=OWNER').json() == []
    assert client.get('/api/shared/decks/' + visible['share_token']).status_code == 200


def test_display_name_cooldown_immutable_username_and_validation(client, monkeypatch):
    now = datetime(2026, 10, 1, 12)
    monkeypatch.setattr(profiles, 'utcnow', lambda: now)
    result = patch(client, display_name='New name', avatar='dog').json()
    assert result['display_name_next_change_at'] == '2026-10-15T12:00:00+00:00'
    assert result['avatar_changes_remaining'] == 9
    assert patch(client, display_name='Another').status_code == 429
    assert patch(client, display_name=' New name ', bio='').json()['display_name_next_change_at'] == result['display_name_next_change_at']
    for values in (
        {'username': 'replacement'}, {'bio': 'x' * 201}, {'avatar': 'https://example.com/img'},
        {'interest_tags': ['Science'] * 2}, {'interest_tags': ['Unknown']},
        {'interest_tags': list(profiles.INTERESTS[:6])}, {'visibility': 'invalid'},
    ):
        assert patch(client, **values).status_code == 422
    with pytest.raises(IntegrityError), client.factory.begin() as db:
        db.execute(text("UPDATE users SET username='replacement' WHERE id=:id"), {'id':client.test_user_id})
    now += timedelta(days=14)
    assert patch(client, display_name='Another').json()['display_name'] == 'Another'


def test_avatar_only_update_keeps_other_settings_and_updates_account(client):
    deck = make_deck(client, 'Featured deck', 'public')
    before = patch(client, bio='My bio', interest_tags=['Science'], visibility='private',
                   featured_deck_id=deck['id']).json()
    assert client.patch('/api/profiles/me', json={'avatar': 'unknown'}).status_code == 422
    result = client.patch('/api/profiles/me', json={'avatar': 'fox'})
    assert result.status_code == 200
    after = result.json()
    for field in ('display_name', 'bio', 'interest_tags', 'visibility', 'featured_deck_id'):
        assert after[field] == before[field]
    assert after['avatar'] == client.get('/api/auth/me').json()['avatar'] == 'fox'
    assert after['avatar_changes_remaining'] == 9


def test_avatar_rolling_limits_and_unchanged_values(client, monkeypatch):
    now = datetime(2026, 10, 1, 12)
    monkeypatch.setattr(profiles, 'utcnow', lambda: now)
    avatars = ('duck', 'fox', 'panda', 'cow', 'hamster', 'fish', 'octopus', 'dog', 'cat', 'chicken')
    for change, avatar in enumerate(avatars):
        saved = patch(client, avatar=avatar).json()
        assert saved['avatar'] == avatar
        assert client.get('/api/profiles/me').json()['avatar'] == avatar
        assert saved['avatar_changes_remaining'] == 9 - change
        now += timedelta(minutes=1)
    assert saved['avatar_next_change_at'] == '2026-10-01T13:00:00+00:00'
    assert patch(client, avatar='dog').status_code == 429
    assert client.patch('/api/profiles/me', json={'avatar': 'dog'}).status_code == 429
    assert patch(client, avatar='chicken', bio='Other edits still work').status_code == 200
    with client.factory() as db:
        assert len(list(db.scalars(select(ProfileAvatarChange)))) == 10
    now += timedelta(minutes=50)
    assert patch(client, avatar='dog').json()['avatar_changes_remaining'] == 0


def test_concurrent_avatar_changes_share_one_remaining_slot(client, monkeypatch):
    now = datetime(2026, 10, 1, 12)
    monkeypatch.setattr(profiles, 'utcnow', lambda: now)
    for change in range(9):
        assert patch(client, avatar='dog' if change % 2 == 0 else 'chicken').status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda avatar: patch(client, avatar=avatar).status_code, ['cat','chicken']))
    assert sorted(outcomes) == [200,429]


def test_featured_deck_ownership_cleanup_and_paginated_list(client):
    path = public_path(client)
    featured = make_deck(client, 'Featured', 'public')
    beta = make_deck(client, 'Beta', 'public')
    alpha = make_deck(client, 'Alpha%', 'public')
    hidden = make_deck(client, 'Private', 'private')
    assert client.post(f"/api/decks/{alpha['id']}/cards", json={'front':'Question','back':'Answer'}).status_code == 201
    outsider = add_user(client, 'outsider')
    from app.models import Deck
    with client.factory.begin() as db:
        other_deck = Deck(owner_id=outsider, title='Other owner', visibility='public')
        db.add(other_deck)
        db.flush()
        foreign_id = other_deck.id
    assert patch(client, featured_deck_id=foreign_id).status_code == 422
    assert patch(client, featured_deck_id=hidden['id']).status_code == 422
    options = client.get('/api/profiles/me/featured-options').json()
    assert {row['id'] for row in options} == {featured['id'], beta['id'], alpha['id']}
    assert patch(client, featured_deck_id=featured['id']).json()['featured_deck']['title'] == 'Featured'
    first = client.get(path + '/decks?sort=alphabetical&limit=1').json()
    assert first['has_more'] and first['items'][0]['title'] == 'Alpha%'
    assert first['items'][0]['card_count'] == 1
    second = client.get(path + '/decks?sort=alphabetical&limit=1&page=2').json()
    assert not second['has_more'] and second['items'][0]['title'] == 'Beta'
    assert client.get(path + '/decks?q=%25').json()['items'] == first['items']
    assert client.get(path + '/decks?sort=oldest').json()['items'][0]['title'] == 'Beta'
    assert client.get(path + '/decks').json()['items'][0]['title'] == 'Alpha%'
    assert client.patch(f"/api/decks/{featured['id']}", json={'visibility':'unlisted'}).status_code == 200
    assert client.get(path).json()['featured_deck'] is None
    assert client.patch(f"/api/decks/{featured['id']}", json={'visibility':'public'}).status_code == 200
    assert client.get(path).json()['featured_deck'] is None
    assert patch(client, featured_deck_id=featured['id']).status_code == 200
    assert client.delete(f"/api/decks/{featured['id']}").status_code == 204
    with client.factory() as db:
        assert db.get(User, client.test_user_id).featured_deck_id is None


def test_report_authorization_limits_and_operator_review(client, monkeypatch, capsys):
    path = public_path(client)
    add_user(client, 'target')
    report_path = '/api/profiles/users/target/reports'
    body = {'reason':'spam', 'explanation':'Synthetic report'}
    assert client.post(path + '/reports',json=body).status_code == 422
    assert client.post(report_path,json={'reason':'invented'}).status_code == 422
    assert client.post(report_path,json={**body,'explanation':'x' * 401}).status_code == 422
    assert client.post(report_path,json=body,headers={'X-CSRF-Token':'incorrect'}).status_code == 403
    assert client.post(report_path,json=body).status_code == 204
    assert client.post(report_path,json=body).status_code == 429
    for number in range(5):
        name = f'target_{number}'
        add_user(client,name)
        response = client.post(f'/api/profiles/users/{name}/reports',json=body)
        assert response.status_code == (204 if number < 4 else 429)
    assert client.get(report_path).status_code == 405
    assert 'reports' not in client.get('/api/profiles/users/target').json()
    with client.factory() as db:
        report = db.scalar(select(ProfileReport).order_by(ProfileReport.id))
    monkeypatch.setattr(cli, 'engine', client.factory.kw['bind'])
    monkeypatch.setattr(cli, 'init_database', lambda: None)
    assert cli.main(['list-profile-reports']) == 0
    assert len(json.loads(capsys.readouterr().out)) == 5
    assert cli.main(['review-profile-report','--report-id',str(report.id)]) == 0
    capsys.readouterr()
    cli.main(['list-profile-reports'])
    assert len(json.loads(capsys.readouterr().out)) == 4
    client.cookies.clear()
    assert client.post(report_path,json=body).status_code == 401


def test_inline_profile_edits_use_catalog_and_bio_limit(client):
    endpoint = '/api/profiles/me'
    original = client.get(endpoint).json()
    assert 'Cryptography' in original['interests']
    assert client.patch(endpoint, json={'interest_tags':['Cryptography','Music']}).status_code == 200
    assert client.patch(endpoint, json={'interest_tags':['Cryptography','Cryptography']}).status_code == 422
    assert client.patch(endpoint, json={'interest_tags':['Unlisted interest']}).status_code == 422
    assert client.patch(endpoint, json={'bio':'a' * 128 + ' '}).status_code == 422
    bio = 'a ' * 64
    response = client.patch(endpoint, json={'bio':bio})
    assert response.status_code == 200
    assert response.json()['bio'] == bio
    assert response.json()['interest_tags'] == ['Cryptography','Music']
    assert response.json()['display_name'] == original['display_name']
    assert response.json()['avatar'] == original['avatar']
