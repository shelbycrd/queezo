from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.service import create_user
from app.main import app
from app.models import Flashcard, StudySession
from conftest import deck


def import_cards(client, deck_id, cards, import_id=None):
    return client.post(f'/api/decks/{deck_id}/cards/import',
                       json={'import_id': str(import_id or uuid4()), 'cards': cards})


def cards_of(client, deck_id):
    return client.get(f'/api/decks/{deck_id}/cards').json()


def test_import_appends_in_order_without_touching_existing_cards_or_history(client):
    deck_id = deck(client, 2)
    before = cards_of(client, deck_id)
    started = client.post(f'/api/decks/{deck_id}/study')
    assert started.status_code == 201
    payload = [{'front': f'  Imported {n}  ', 'back': f'Answer {n}'} for n in range(3)]
    response = import_cards(client, deck_id, payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body['imported'] == 3
    assert [card['front'] for card in body['cards']] == ['Imported 0', 'Imported 1', 'Imported 2']
    after = cards_of(client, deck_id)
    assert after[:2] == before  # existing cards unchanged
    assert [card['front'] for card in after[2:]] == ['Imported 0', 'Imported 1', 'Imported 2']
    assert after[2]['id'] < after[3]['id'] < after[4]['id']
    with client.factory() as db:
        imported = db.scalars(select(Flashcard).where(Flashcard.id.in_([card['id'] for card in after[2:]])))
        assert all(card.front_image is None and card.back_image is None and card.card_type == 'two_sided'
                   for card in imported)
        assert db.scalar(select(StudySession.status).where(StudySession.id == started.json()['id'])) == 'active'
    assert client.get(f'/api/decks/{deck_id}').json()['card_count'] == 5


def test_invalid_entries_reject_the_whole_import(client):
    deck_id = deck(client, 1)
    cases = [
        [],                                                        # empty list
        [{'front': 'Q'}],                                          # missing back
        [{'front': '   ', 'back': 'A'}],                           # whitespace only
        [{'front': 'Q', 'back': 'A', 'front_image': None}],        # unsupported field
        [{'front': 5, 'back': 'A'}],                               # not a string
        [{'front': 'x' * 251, 'back': 'A'}],                       # over the editor limit
        [{'front': 'Q', 'back': 'A'}, {'front': 'See https://example.com', 'back': 'A'}],  # link in card 2
        ['not an object'],
    ]
    for cards in cases:
        response = import_cards(client, deck_id, cards)
        assert response.status_code == 422, (cards, response.text)
    assert client.post(f'/api/decks/{deck_id}/cards/import', json={'cards': [{'front': 'Q', 'back': 'A'}]}).status_code == 422
    assert client.post(f'/api/decks/{deck_id}/cards/import',
                       json={'import_id': str(uuid4()), 'cards': [{'front': 'Q', 'back': 'A'}], 'deck': 1}).status_code == 422
    assert len(cards_of(client, deck_id)) == 1  # nothing partial was saved
    assert import_cards(client, deck_id, [{'front': 'x' * 250, 'back': 'y' * 250}]).status_code == 201


def test_card_limit_is_checked_for_the_whole_batch(client):
    deck_id = deck(client, 148)
    too_many = [{'front': f'Q{n}', 'back': 'A'} for n in range(3)]
    response = import_cards(client, deck_id, too_many)
    assert response.status_code == 409
    assert 'room for 2 more flashcards' in response.json()['error']['message']
    assert len(cards_of(client, deck_id)) == 148
    assert import_cards(client, deck_id, too_many[:2]).status_code == 201
    assert import_cards(client, deck_id, too_many[:1]).status_code == 409
    over = [{'front': f'Q{n}', 'back': 'A'} for n in range(151)]
    assert import_cards(client, deck(client, 0), over).status_code == 422


def test_repeated_or_concurrent_submissions_save_once(client):
    deck_id = deck(client, 0)
    import_id = uuid4()
    payload = [{'front': 'Q', 'back': 'A'}]
    with ThreadPoolExecutor(6) as pool:
        codes = list(pool.map(lambda _: import_cards(client, deck_id, payload, import_id).status_code, range(6)))
    assert sorted(codes) == [201] + [409] * 5
    assert len(cards_of(client, deck_id)) == 1
    retry = import_cards(client, deck_id, payload, import_id)
    assert retry.status_code == 409 and retry.json()['error']['message'] == 'This import was already saved.'
    # A failed attempt does not consume its ID, so the same import can be retried.
    failed_id = uuid4()
    full = deck(client, 150)
    assert import_cards(client, full, payload, failed_id).status_code == 409
    assert import_cards(client, deck_id, payload, failed_id).status_code == 201


def test_imports_require_the_deck_owner_and_csrf(client):
    deck_id = deck(client, 1)
    with client.factory.begin() as db:
        create_user(db, 'other@example.com', 'another synthetic passphrase', username='other_user')
    other = TestClient(app)
    login = other.post('/api/auth/login', json={'email': 'other@example.com', 'password': 'another synthetic passphrase'})
    other.headers['x-csrf-token'] = login.json()['csrf_token']
    payload = [{'front': 'Q', 'back': 'A'}]
    assert import_cards(other, deck_id, payload).status_code == 404
    assert import_cards(TestClient(app), deck_id, payload).status_code in (401, 403)
    token = client.headers.pop('X-CSRF-Token')
    assert import_cards(client, deck_id, payload).status_code == 403
    client.headers['X-CSRF-Token'] = token
    assert len(cards_of(client, deck_id)) == 1


def test_import_never_calls_ollama(client, monkeypatch):
    from app.services import distractors

    async def forbidden(*args, **kwargs):
        raise AssertionError('Import must not generate distractors.')
    monkeypatch.setattr(distractors, 'generate_distractors', forbidden)
    assert import_cards(client, deck(client, 0), [{'front': 'Q', 'back': 'A'}]).status_code == 201
    with client.factory() as db:
        assert db.scalar(select(Flashcard.front)) == 'Q'
