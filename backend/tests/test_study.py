from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from app.models import StudySessionCard
from conftest import deck, presentation, review


def start(client, deck_id):
    response = client.post(f'/api/decks/{deck_id}/study')
    assert response.status_code == 201, response.text
    return response.json()


def test_reveal_hides_answer_and_gates_rating(client):
    deck_id = deck(client)
    state = start(client,deck_id)
    assert 'back' not in state['current_card']
    path = f"/api/study/{state['id']}"
    assert client.post(f'{path}/rate', json={**presentation(state),'difficulty':'easy'}).status_code == 409
    assert client.get(path).json()['total_reviews'] == 0
    revealed = client.post(f'{path}/reveal', json=presentation(state)).json()
    assert revealed['current_card']['back'] == 'Answer 0'
    assert client.get(path).json()['revealed'] is True
    assert client.post(f'{path}/reveal', json=presentation(state)).status_code == 200
    assert client.post(f'{path}/rate', json={**presentation(state),'difficulty':'impossible'}).status_code == 422
    next_state = review(client,state)
    assert 'back' not in next_state['current_card']
    assert next_state['revealed'] is False


@pytest.mark.parametrize('difficulty,target',[('easy',2),('normal',3),('hard',4)])
@pytest.mark.parametrize('count',[1,2,3])
def test_small_decks_complete_and_summary_is_accurate(client,difficulty,target,count):
    deck_id = deck(client,count)
    state = start(client,deck_id)
    seen = Counter()
    last = None
    while state['status'] == 'active':
        assert state['total_reviews'] < count*4
        card_id = state['current_card']['id']
        with client.factory() as db:
            remaining = list(db.scalars(select(StudySessionCard).where(StudySessionCard.session_id == state['id'], StudySessionCard.completed.is_(False))))
            if len(remaining) > 1:
                assert card_id != last
        seen[card_id] += 1
        last = card_id
        state = review(client,state,difficulty)
    assert state['status'] == 'completed'
    assert state['completed_cards'] == count
    assert state['current_card'] is None
    assert state['total_reviews'] == count*target
    assert list(seen.values()) == [target]*count
    summary = client.get(f"/api/study/{state['id']}/summary").json()
    assert summary['total_unique_cards'] == count
    assert summary['total_reviews'] == count*target
    assert summary[f'{difficulty}_count'] == count*target
    assert summary['easy_count']+summary['normal_count']+summary['hard_count'] == summary['total_reviews']
    assert summary['duration_seconds'] >= 0
    assert summary['started_at'].endswith('+00:00')
    assert summary['completed_at'] is not None
    assert client.get(f'/api/decks/{deck_id}/sessions').json()[0]['status'] == 'completed'


def test_changed_difficulty_reduces_target(client):
    state = start(client,deck(client))
    state = review(client,state,'hard')
    assert state['current_card']['target_reviews'] == 4
    state = review(client,state,'easy')
    assert state['status'] == 'completed'
    assert state['total_reviews'] == 2


def test_changed_difficulty_increases_target(client):
    state = start(client,deck(client))
    for difficulty in ['easy','hard','normal']:
        state = review(client,state,difficulty)
    assert state['status'] == 'completed'
    assert state['total_reviews'] == 3


def test_duplicate_and_out_of_sequence_requests(client):
    state = start(client,deck(client,2))
    path = f"/api/study/{state['id']}"
    original = presentation(state)
    assert client.post(f'{path}/reveal',json={**original,'presentation_number':2}).status_code == 409
    assert client.post(f'{path}/reveal',json={**original,'presentation_token':'x'*36}).status_code == 409
    state = review(client,state)
    assert client.post(f'{path}/rate',json={**original,'difficulty':'hard'}).status_code == 409
    assert client.post(f'{path}/reveal',json=original).status_code == 409
    assert client.get(path).json()['total_reviews'] == 1


def test_concurrent_duplicate_rating_counts_once(client):
    state = start(client,deck(client))
    path = f"/api/study/{state['id']}"
    client.post(f'{path}/reveal',json=presentation(state))
    def submit(_):
        return client.post(f'{path}/rate',json={**presentation(state),'difficulty':'normal'}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(submit,range(2))) == [200,409]
    assert client.get(path).json()['total_reviews'] == 1


def test_all_cards_are_two_sided_and_require_reveal(client):
    state = start(client,deck(client))
    assert state['current_card']['front'] == 'Question 0'
    assert state['current_card']['card_type'] == 'two_sided'
    assert 'back' not in state['current_card']
    state = review(client,state)
    assert state['current_card']['card_type'] == 'two_sided'
    revealed = client.post(f"/api/study/{state['id']}/reveal",json=presentation(state)).json()
    assert revealed['current_card']['back'] == 'Answer 0'


def test_exit_is_idempotent_and_keeps_deck(client):
    deck_id = deck(client,2)
    state = start(client,deck_id)
    assert client.get(f"/api/study/{state['id']}/summary").status_code == 409
    path = f"/api/study/{state['id']}"
    assert client.post(f'{path}/exit').json()['status'] == 'exited'
    assert client.post(f'{path}/exit').json()['status'] == 'exited'
    assert client.post(f'{path}/rate',json={**presentation(state),'difficulty':'easy'}).status_code == 409
    assert len(client.get(f'/api/decks/{deck_id}/cards').json()) == 2
    assert client.get(f'{path}/summary').json()['total_reviews'] == 0


def test_snapshot_survives_card_edits_and_deletion(client):
    deck_id = deck(client)
    state = start(client,deck_id)
    card = client.get(f'/api/decks/{deck_id}/cards').json()[0]
    client.patch(f"/api/cards/{card['id']}",json={'front':'Edited question','back':'Edited answer'})
    client.delete(f"/api/cards/{card['id']}")
    assert client.get(f"/api/study/{state['id']}").json()['current_card']['front'] == 'Question 0'
    state = review(client,state)
    state = review(client,state)
    assert state['status'] == 'completed'
    assert client.get(f"/api/study/{state['id']}/summary").json()['total_unique_cards'] == 1


def test_independent_shuffle_and_initial_encounters_not_creation_order(client):
    deck_id = deck(client,6)
    initial_cards = client.get(f'/api/decks/{deck_id}/cards').json()
    creation_order = [card['front'] for card in initial_cards]
    orders = []
    for _ in range(3):
        state = start(client,deck_id)
        with client.factory() as db:
            saved_order = [card.front for card in db.scalars(select(StudySessionCard).where(StudySessionCard.session_id == state['id']).order_by(StudySessionCard.initial_order))]
        assert saved_order != creation_order
        seen = []
        while state['status'] == 'active':
            front = state['current_card']['front']
            if front not in seen:
                seen.append(front)
            state = review(client,state)
        assert seen == saved_order
        orders.append(saved_order)
    # Distinct session seeds are tested directly rather than asserting random
    # permutations must differ, which would be probabilistically flaky.
    assert len(orders) == 3


def test_study_again_is_fresh(client):
    deck_id = deck(client)
    state = start(client,deck_id)
    state = review(client,review(client,state))
    new = start(client,deck_id)
    assert new['id'] != state['id']
    assert new['total_reviews'] == 0
    assert new['completed_cards'] == 0
    assert new['current_card']['review_count'] == 0



def test_previous_session_returns_only_the_latest_of_each_mode(client):
    from app.services import multiple_choice

    deck_id = deck(client)
    first, latest = (start(client, deck_id) for _ in range(2))
    first_mc, latest_mc = (multiple_choice.create_session(deck_id, client.test_user_id)[0] for _ in range(2))
    base = f'/api/decks/{deck_id}'
    classic_history, mc_history = base + '/sessions', base + '/multiple-choice/sessions'

    assert [item['session_id'] for item in client.get(classic_history + '?limit=1').json()] == [latest['id']]
    assert [item['id'] for item in client.get(mc_history + '?limit=1').json()] == [latest_mc['id']]
    assert len(client.get(classic_history).json()) == len(client.get(mc_history).json()) == 2
    assert client.get(f"/api/study/{first['id']}").status_code == 200
    assert client.get(f"/api/multiple-choice/{first_mc['id']}").status_code == 200
