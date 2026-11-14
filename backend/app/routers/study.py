import random
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_user
from app.database import get_db, get_write_db
from app.models import Deck, Flashcard, StudyReview, StudySession, StudySessionCard, User, utcnow
from app.routers.decks import owned_query, require
from app.schemas import PresentationInput, RatingInput
from app.services.presenters import session_view, summary_view
from app.services.study_scheduler import apply_rating, choose_next

router = APIRouter(prefix="/api", tags=["Study sessions"])


def session_cards(db, session, user):
    return list(db.scalars(owned_query(StudySessionCard, user).where(
        StudySessionCard.session_id == session.id).order_by(StudySessionCard.initial_order)))


def require_presentation(session, data):
    if session.status != "active":
        raise HTTPException(409, "This study session is no longer active.")
    if (data.presentation_number != session.total_reviews + 1
            or data.presentation_token != session.presentation_token):
        raise HTTPException(409, "This presentation has changed or was already rated. Reload the session.")


@router.post("/decks/{deck_id}/study", status_code=201)
def start_study(deck_id: int, user: User = Depends(require_user), db: Session = Depends(get_write_db)):
    deck = require(db, Deck, deck_id, user)
    cards = list(db.scalars(owned_query(Flashcard, user).where(Flashcard.deck_id == deck_id).order_by(Flashcard.id)))
    if not cards:
        raise HTTPException(409, "Add at least one flashcard before starting a study session.")
    seed = str(uuid4())
    rng = random.Random(seed)
    rng.shuffle(cards)
    # A shuffle may legitimately leave input unchanged. Avoid that particular
    # result for decks > 1 so the first pass is never creation order.
    if len(cards) > 1 and [c.id for c in cards] == sorted(c.id for c in cards):
        cards = cards[1:] + cards[:1]
    session = StudySession(id=str(uuid4()), deck_id=deck_id, deck_title=deck.title, owner_id=user.id,
                           random_seed=seed, total_cards=len(cards))
    db.add(session)
    db.flush()
    snapshots = [StudySessionCard(session_id=session.id, flashcard_id=card.id,
                 card_type=card.card_type, front=card.front, back=card.back,
                 initial_order=index) for index, card in enumerate(cards)]
    db.add_all(snapshots)
    db.flush()
    session.current_card_id = snapshots[0].id
    session.presentation_token = str(uuid4())
    return session_view(db, session)


@router.get("/study/{session_id}")
def get_session(session_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    return session_view(db, require(db, StudySession, session_id, user))


@router.post("/study/{session_id}/reveal")
def reveal(session_id: str, data: PresentationInput, user: User = Depends(require_user), db: Session = Depends(get_write_db)):
    session = require(db, StudySession, session_id, user)
    require_presentation(session, data)
    session.revealed = True
    return session_view(db, session)


@router.post("/study/{session_id}/rate")
def rate(session_id: str, data: RatingInput, user: User = Depends(require_user), db: Session = Depends(get_write_db)):
    session = require(db, StudySession, session_id, user)
    require_presentation(session, data)
    if not session.revealed:
        raise HTTPException(409, "Reveal the answer before rating this card.")
    current = db.scalar(owned_query(StudySessionCard, user).where(
        StudySessionCard.id == session.current_card_id, StudySessionCard.session_id == session.id))
    if current is None:
        raise HTTPException(404, "StudySessionCard not found.")
    db.add(StudyReview(session_id=session.id, session_card_id=current.id,
           difficulty=data.difficulty, presentation_number=data.presentation_number,
           presentation_token=data.presentation_token))
    rng = random.Random(f"{session.random_seed}:{session.total_reviews}")
    apply_rating(current, data.difficulty, session.virtual_position, rng)
    session.total_reviews += 1
    field = f"{data.difficulty}_count"
    setattr(session, field, getattr(session, field) + 1)
    cards = session_cards(db, session, user)
    next_card, position = choose_next(cards, session.virtual_position + 1, current.id, rng)
    session.virtual_position = position
    session.revealed = False
    session.current_card_id = next_card.id if next_card else None
    session.presentation_token = str(uuid4()) if next_card else None
    if next_card is None:
        session.status = "completed"
        session.completed_at = utcnow()
    return session_view(db, session)


@router.post("/study/{session_id}/exit")
def exit_session(session_id: str, user: User = Depends(require_user), db: Session = Depends(get_write_db)):
    session = require(db, StudySession, session_id, user)
    if session.status == "active":
        session.status = "exited"
        session.completed_at = utcnow()
        session.current_card_id = None
        session.presentation_token = None
        session.revealed = False
    return session_view(db, session)


@router.get("/study/{session_id}/summary")
def get_summary(session_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    session = require(db, StudySession, session_id, user)
    if session.status == "active":
        raise HTTPException(409, "This session is still active.")
    return summary_view(db, session)
