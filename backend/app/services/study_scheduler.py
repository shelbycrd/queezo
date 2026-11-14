"""Pure scheduler: positions count presentations, never elapsed wall-clock time."""
from dataclasses import dataclass
from random import Random

TARGETS = {"easy": 2, "normal": 3, "hard": 4}
INTERVALS = {"easy": (5, 8), "normal": (3, 5), "hard": (1, 3)}
WEIGHTS = {None: 2, "easy": 1, "normal": 2, "hard": 3}


@dataclass
class CardState:
    id: int
    review_count: int = 0
    latest_difficulty: str | None = None
    target_reviews: int = 2
    next_eligible_position: int = 0
    completed: bool = False
    initial_order: int = 0


def apply_rating(card, difficulty: str, position: int, rng: Random):
    card.review_count += 1
    card.latest_difficulty = difficulty
    card.target_reviews = TARGETS[difficulty]
    card.completed = card.review_count >= card.target_reviews
    # +1 means a gap of 1 really leaves one OTHER presentation between repeats.
    card.next_eligible_position = position + rng.randint(*INTERVALS[difficulty]) + 1


def choose_next(cards, position: int, last_id: int | None, rng: Random):
    pending = [card for card in cards if not card.completed]
    if not pending:
        return None, position
    alternatives = [card for card in pending if card.id != last_id]
    candidates = alternatives or pending
    # Keep first encounters in the session's pre-shuffled order, while allowing
    # already-seen, eligible cards to compete with the next unseen card.
    unseen = [card for card in candidates if card.review_count == 0]
    if unseen:
        first_unseen = min(unseen, key=lambda card: card.initial_order)
        candidates = [card for card in candidates if card.review_count > 0 or card is first_unseen]
    eligible = [card for card in candidates if card.next_eligible_position <= position]
    if not eligible:
        position = max(position, min(card.next_eligible_position for card in candidates))
        eligible = [card for card in candidates if card.next_eligible_position <= position]
    selected = rng.choices(eligible, weights=[WEIGHTS[c.latest_difficulty] for c in eligible], k=1)[0]
    return selected, position
