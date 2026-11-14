from random import Random

import pytest

from app.services.study_scheduler import CardState, INTERVALS, apply_rating, choose_next


@pytest.mark.parametrize('seed',range(30))
@pytest.mark.parametrize('size',[1,2,3,10,150])
def test_arbitrary_rating_changes_always_finish(seed,size):
    rng = Random(seed)
    cards = [CardState(id=index,initial_order=index) for index in range(size)]
    position = 0
    last = None
    events = []
    while True:
        selected,position = choose_next(cards,position,last,rng)
        if selected is None:
            break
        assert not selected.completed
        if last is not None and sum(not card.completed for card in cards) > 1:
            assert selected.id != last
        apply_rating(selected,rng.choice(['easy','normal','hard']),position,rng)
        events.append(selected.id)
        assert len(events) <= size*4
        last = selected.id
        position += 1
    assert all(card.completed and card.review_count >= card.target_reviews for card in cards)
    assert len(events) >= size*2


def test_earliest_virtual_position_does_not_fabricate_reviews():
    cards = [CardState(id=1,review_count=1,next_eligible_position=20),CardState(id=2,review_count=1,next_eligible_position=10)]
    selected,position = choose_next(cards,2,None,Random(1))
    assert selected.id == 2
    assert position == 10
    assert [card.review_count for card in cards] == [1,1]


def test_completed_cards_excluded_and_latest_target_used():
    card = CardState(id=1)
    apply_rating(card,'hard',0,Random(1))
    assert not card.completed and card.target_reviews == 4
    apply_rating(card,'easy',2,Random(1))
    assert card.completed and card.target_reviews == 2 and card.review_count == 2
    assert choose_next([card],3,None,Random(1))[0] is None


def test_intervals_are_other_presentations():
    for difficulty,(low,high) in INTERVALS.items():
        card = CardState(id=1)
        apply_rating(card,difficulty,7,Random(1))
        assert 7+low+1 <= card.next_eligible_position <= 7+high+1


def test_deterministic_with_seed():
    cards = [CardState(id=i,review_count=1,latest_difficulty='hard' if i%2 else 'easy') for i in range(10)]
    def sequence():
        rng = Random(42)
        return [choose_next(cards,0,None,rng)[0].id for _ in range(20)]
    assert sequence() == sequence()


def test_hard_gets_more_weight_without_fixed_order():
    cards = [CardState(id=1,review_count=1,latest_difficulty='easy'),CardState(id=2,review_count=1,latest_difficulty='hard')]
    rng = Random(19)
    selected = [choose_next(cards,0,None,rng)[0].id for _ in range(2000)]
    hard = selected.count(2)
    assert 1300 < hard < 1700
