import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.database import init_database, make_engine
from app.models import Deck, Flashcard
from app.services.content_policy import no_urls


def make_deck(client, visibility='private', title='Biology'):
    response = client.post('/api/decks',json={'title':title,'visibility':visibility})
    assert response.status_code == 201, response.text
    deck = response.json()
    assert client.post(f"/api/decks/{deck['id']}/cards",json={'front':'What is a cell?','back':'A unit of life.'}).status_code == 201
    return deck


def switch_account(client):
    response = client.post('/api/auth/signup',json={'display_name':'Other learner','username':'other_learner',
        'email':'other-learner@example.com','password':'Quiet maple test secret','confirm_password':'Quiet maple test secret'})
    assert response.status_code == 201
    client.headers['X-CSRF-Token'] = response.json()['csrf_token']
    return response.json()


def test_default_private_and_invalid_visibility(client):
    deck = client.post('/api/decks',json={'title':'Private default'}).json()
    assert deck['visibility'] == 'private'
    assert len(deck['share_token']) >= 32
    assert client.get('/api/community/decks').json() == []
    assert client.get(f"/api/shared/decks/{deck['share_token']}").status_code == 404
    for value in ('Public','unknown',None,True):
        assert client.post('/api/decks',json={'title':'Bad','visibility':value}).status_code == 422
        assert client.patch(f"/api/decks/{deck['id']}",json={'visibility':value}).status_code == 422


def test_public_unlisted_readonly_and_private_revocation(client):
    public = make_deck(client,'public')
    unlisted = make_deck(client,'unlisted','Unlisted biology')
    private = make_deck(client)
    reader = switch_account(client)
    feed = client.get('/api/community/decks').json()
    assert [item['share_token'] for item in feed] == [public['share_token']]
    for deck in (public,unlisted):
        result = client.get(f"/api/shared/decks/{deck['share_token']}").json()
        assert result['cards'][0]['back'] == 'A unit of life.'
        assert not ({'owner_id','id','email','username'} & result.keys())
        assert not ({'id','deck_id'} & result['cards'][0].keys())
        for path in (f"/api/decks/{deck['id']}",f"/api/decks/{deck['id']}/cards",f"/api/decks/{deck['id']}/sessions"):
            assert client.get(path).status_code == 404
        assert client.patch(f"/api/decks/{deck['id']}",json={'visibility':'private'}).status_code == 404
        assert client.delete(f"/api/decks/{deck['id']}").status_code == 404
        assert client.post(f"/api/decks/{deck['id']}/study").status_code == 404
    assert client.get(f"/api/shared/decks/{private['share_token']}").status_code == 404
    assert client.post(f"/api/shared/decks/{private['share_token']}/copy").status_code == 404
    assert client.get('/api/decks').json() == []
    copied = client.post(f"/api/shared/decks/{unlisted['share_token']}/copy").json()
    assert copied['visibility'] == 'private' and copied['share_token'] != unlisted['share_token']
    assert copied['id'] != unlisted['id']
    assert client.get(f"/api/decks/{copied['id']}/cards").json()[0]['back'] == 'A unit of life.'
    assert client.post(f"/api/decks/{copied['id']}/study").status_code == 201
    with client.factory() as db:
        assert db.get(Deck,copied['id']).owner_id == reader['id']
        db.get(Deck,public['id']).visibility = 'private'
        db.commit()
    assert client.get('/api/community/decks').json() == []
    assert client.get(f"/api/shared/decks/{public['share_token']}").status_code == 404
    assert client.post(f"/api/shared/decks/{public['share_token']}/copy").status_code == 404


def test_community_limit_order_and_unassigned_exclusion(client):
    tokens = []
    for index in range(23):
        tokens.append(client.post('/api/decks',json={'title':f'Public {index}','visibility':'public'}).json()['share_token'])
    with client.factory() as db:
        db.add(Deck(title='Unassigned public',visibility='public'))
        db.commit()
    feed = client.get('/api/community/decks').json()
    assert len(feed) == 20
    assert [item['share_token'] for item in feed] == list(reversed(tokens))[:20]


def test_owner_visibility_changes_preserve_title_and_rename_preserves_visibility(client):
    deck = make_deck(client)
    changed = client.patch(f"/api/decks/{deck['id']}",json={'visibility':'public'}).json()
    assert changed['title'] == 'Biology'
    assert changed['share_token'] != deck['share_token']
    renamed = client.patch(f"/api/decks/{deck['id']}",json={'title':'Cell biology'}).json()
    assert renamed['visibility'] == 'public'
    assert client.patch(f"/api/decks/{deck['id']}",json={'visibility':'private'}).status_code == 200
    assert client.get(f"/api/shared/decks/{deck['share_token']}").status_code == 404


def test_shared_routes_require_auth_and_copy_requires_csrf(client):
    deck = make_deck(client,'public')
    client.headers.pop('X-CSRF-Token')
    assert client.post(f"/api/shared/decks/{deck['share_token']}/copy").status_code == 403
    client.cookies.clear()
    assert client.get('/api/community/decks').status_code == 401
    assert client.get(f"/api/shared/decks/{deck['share_token']}").status_code == 401
    assert client.post(f"/api/shared/decks/{deck['share_token']}/copy").status_code == 401


@pytest.mark.parametrize('value',[
    'https://example.com','HTTP://EXAMPLE.COM/path','ftp://host/file','www.example.com','example.org/path',
    '//example.net/path','127.0.0.1:8080','localhost:8080/path','[::1]:8000',
    'mailto:person@example.com','javascript:alert(1)','data:text/html;base64,abc','custom://server/path',
    'hxxps://example[.]com','https%3A%2F%2Fexample.com','https&#58;//example.com',
    'https%EF%BC%9A%EF%BC%8F%EF%BC%8Fexample%EF%BC%8Ecom',
    'ｅｘａｍｐｌｅ．ｃｏｍ','htt\u200bps://example.com','https:\\example.com','example.xn--p1ai',
])
def test_url_policy_variants(value):
    with pytest.raises(ValueError):
        no_urls('Study reference: '+value)


@pytest.mark.parametrize('value',['Grade 1.75','3.14159','Question: explain cells','Answer: A unit of life.',
    '1. First item\n2. Second item','Anatomy and physiology','E.g. cells divide.'])
def test_ordinary_study_text_allowed(value):
    assert no_urls(value) == value


def test_url_policy_enforced_on_create_patch_and_publish_legacy(client):
    deck = make_deck(client)
    card = client.get(f"/api/decks/{deck['id']}/cards").json()[0]
    assert client.post('/api/decks',json={'title':'Visit example.com'}).status_code == 422
    assert client.patch(f"/api/decks/{deck['id']}",json={'title':'Visit www.example.com'}).status_code == 422
    for field in ('front','back'):
        assert client.post(f"/api/decks/{deck['id']}/cards",json={'front':'Q','back':'A',field:'https://example.com'}).status_code == 422
        assert client.patch(f"/api/cards/{card['id']}",json={field:'example.com'}).status_code == 422
    with client.factory() as db:
        db.get(Flashcard,card['id']).back = 'Old https://example.com reference'
        db.commit()
    assert client.patch(f"/api/decks/{deck['id']}",json={'visibility':'public'}).status_code == 422
    assert client.get(f"/api/decks/{deck['id']}").json()['visibility'] == 'private'
    with client.factory() as db:
        db.get(Deck,deck['id']).visibility = 'public'
        db.commit()
    before = len(client.get('/api/decks').json())
    assert client.post(f"/api/shared/decks/{deck['share_token']}/copy").status_code == 422
    assert len(client.get('/api/decks').json()) == before


def test_sharing_migration_is_private_idempotent_and_preserves_rows(tmp_path):
    engine = make_engine(f'sqlite:///{tmp_path / "legacy.db"}')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE decks (id INTEGER PRIMARY KEY, title TEXT NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)'))
        db.execute(text("INSERT INTO decks VALUES (7,'Preserved deck','2026-01-01','2026-01-01')"))
    init_database(engine)
    with Session(engine) as db:
        deck = db.get(Deck,7)
        token = deck.share_token
        assert deck.title == 'Preserved deck' and deck.visibility == 'private'
        assert len(token) >= 32
    init_database(engine)
    with Session(engine) as db:
        assert db.get(Deck,7).share_token == token
    engine.dispose()
