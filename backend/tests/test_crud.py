from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from app.database import make_engine
from app.models import Deck, Flashcard, StudyReview, StudySession, StudySessionCard
from sqlalchemy.orm import Session
from conftest import deck, review


def test_deck_and_card_crud(client):
    deck_id = deck(client, 0)
    assert client.get('/api/decks').json()[0]['card_count'] == 0
    assert client.patch(f'/api/decks/{deck_id}', json={'title':'  Memory Management  '}).json()['title'] == 'Memory Management'
    card = client.post(f'/api/decks/{deck_id}/cards', json={'card_type':'two_sided','front':'What is LRU?','back':'Least Recently Used'}).json()
    assert client.get(f"/api/cards/{card['id']}").json()['back'] == 'Least Recently Used'
    assert client.patch(f"/api/cards/{card['id']}", json={'front':'LRU stands for?'}).json()['front'] == 'LRU stands for?'
    assert client.patch(f"/api/cards/{card['id']}", json={'card_type':'one_sided'}).status_code == 422
    changed = client.patch(f"/api/cards/{card['id']}", json={'card_type':'one_sided','back':None})
    assert changed.status_code == 422
    assert client.get(f"/api/cards/{card['id']}").json()['back'] == 'Least Recently Used'
    assert client.get('/api/dashboard').json() == {'deck_count':1,'card_count':1}
    assert client.delete(f"/api/cards/{card['id']}").status_code == 204
    assert client.get(f"/api/cards/{card['id']}").status_code == 404
    assert client.delete(f'/api/decks/{deck_id}').status_code == 204
    assert client.get('/api/dashboard').json() == {'deck_count':0,'card_count':0}


@pytest.mark.parametrize('payload', [{}, {'title':''}, {'title':'   '}, {'title':'x'*121}, {'title':None}, {'title':123}, {'title':'Good','unknown':1}])
def test_invalid_decks(client, payload):
    response = client.post('/api/decks', json=payload)
    assert response.status_code == 422
    assert 'message' in response.json()['error']


@pytest.mark.parametrize('payload', [
    {'card_type':'two_sided','front':'Q'},
    {'card_type':'two_sided','front':'Q','back':'  '},
    {'front':'Q','back':None},
    {'front':'Q','back':''},
    {'card_type':'one_sided','front':''},
    {'card_type':'one_sided','front':'   '},
    {'card_type':'one_sided','front':'Q','back':'Answer'},
    {'card_type':'invalid','front':'Q'},
    {'card_type':'two_sided','front':'x'*10001,'back':'A'},
    {'card_type':'two_sided','front':'Q','back':'x'*10001},
    {'card_type':'two_sided','front':None,'back':'A'},
])
def test_invalid_cards(client, payload):
    deck_id = deck(client, 0)
    assert client.post(f'/api/decks/{deck_id}/cards', json=payload).status_code == 422


def test_partial_card_validation(client):
    deck_id = deck(client)
    card = client.get(f'/api/decks/{deck_id}/cards').json()[0]
    for payload in [{'front':None},{'card_type':None},{'front':'  '},{'back':None},{'back':''},{'back':'  '},{'card_type':'one_sided'}]:
        assert client.patch(f"/api/cards/{card['id']}",json=payload).status_code == 422
    assert client.patch(f"/api/cards/{card['id']}",json={'back':'New answer'}).status_code == 200
    assert client.get(f"/api/cards/{card['id']}").json()['card_type'] == 'two_sided'


def test_limit_and_concurrent_last_slot(client):
    deck_id = deck(client, 149)
    def add(_):
        return client.post(f'/api/decks/{deck_id}/cards', json={'front':'Last slot','back':'Answer'}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(add, range(2)))
    assert sorted(statuses) == [201,409]
    assert client.get(f'/api/decks/{deck_id}').json()['card_count'] == 150
    assert add(0) == 409


def test_deck_cascade_removes_all_study_data(client):
    deck_id = deck(client)
    state = client.post(f'/api/decks/{deck_id}/study').json()
    state = review(client, state)
    assert client.delete(f'/api/decks/{deck_id}').status_code == 204
    with client.factory() as db:
        for model in [Deck,Flashcard,StudySession,StudySessionCard,StudyReview]:
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_persistence_after_new_engine(client):
    deck_id = deck(client)
    state = client.post(f'/api/decks/{deck_id}/study').json()
    state = review(client, state, 'hard')
    other_engine = make_engine(client.database_url)
    with Session(other_engine) as db:
        assert db.get(Deck,deck_id).title == 'Operating Systems'
        assert db.scalar(select(func.count()).select_from(Flashcard)) == 1
        saved = db.get(StudySession,state['id'])
        assert saved.total_reviews == 1
        assert saved.presentation_token == state['presentation_token']
        assert db.scalar(select(StudySessionCard)).latest_difficulty == 'hard'
    other_engine.dispose()


def test_missing_resources_and_empty_study(client):
    assert client.get('/api/decks/999').status_code == 404
    assert client.get('/api/decks/999/cards').status_code == 404
    assert client.post('/api/decks/999/study').status_code == 404
    deck_id = deck(client,0)
    assert client.post(f'/api/decks/{deck_id}/study').status_code == 409
    assert client.get('/api/study/missing').status_code == 404
    assert client.get('/api/health').json() == {'status':'ok'}
    assert 'error' in client.get('/api/nonexistent').json()
    assert 'error' in client.put('/api/decks').json()
