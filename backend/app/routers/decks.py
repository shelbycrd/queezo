from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_user
from app.database import get_db, get_write_db
from app.models import Deck, Flashcard, StudySession, StudySessionCard, User, utcnow
from app.schemas import CardInput, CardPatch, DeckInput, DeckPatch
from app.services.content_policy import no_urls
import secrets
from app.services.presenters import card_view, deck_view, summary_view

router = APIRouter(prefix="/api", tags=["Decks and flashcards"])


def owned_query(model, user):
    """Scope every lookup in SQL; unassigned legacy records remain private."""
    if model is Deck:
        return select(Deck).where(Deck.owner_id == user.id)
    if model is Flashcard:
        return select(Flashcard).join(Deck, Flashcard.deck_id == Deck.id).where(Deck.owner_id == user.id)
    if model is StudySession:
        return select(StudySession).join(Deck, StudySession.deck_id == Deck.id).where(
            StudySession.owner_id == user.id, Deck.owner_id == user.id)
    if model is StudySessionCard:
        return select(StudySessionCard).join(StudySession, StudySessionCard.session_id == StudySession.id).join(
            Deck, StudySession.deck_id == Deck.id).where(
                StudySession.owner_id == user.id, Deck.owner_id == user.id)
    raise ValueError("Unsupported ownership-scoped resource")


def require(db, model, identity, user):
    value = db.scalar(owned_query(model, user).where(model.id == identity))
    if value is None:
        raise HTTPException(404, f"{model.__name__} not found.")
    return value


@router.get("/dashboard")
def dashboard(user: User = Depends(require_user), db: Session = Depends(get_db)):
    return {"deck_count": db.scalar(select(func.count()).select_from(Deck).where(Deck.owner_id == user.id)),
            "card_count": db.scalar(select(func.count()).select_from(Flashcard).join(
                Deck, Flashcard.deck_id == Deck.id).where(Deck.owner_id == user.id))}


@router.get("/decks")
def list_decks(user: User = Depends(require_user), db: Session = Depends(get_db)):
    return [deck_view(db, deck) for deck in db.scalars(owned_query(Deck, user).order_by(Deck.updated_at.desc(), Deck.id.desc()))]


@router.post("/decks", status_code=201)
def create_deck(data: DeckInput, user: User = Depends(require_user), db: Session = Depends(get_write_db)):
    deck = Deck(title=data.title, visibility=data.visibility, owner_id=user.id)
    db.add(deck)
    db.flush()
    return deck_view(db, deck)


@router.get("/decks/{deck_id}")
def get_deck(deck_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    return deck_view(db, require(db, Deck, deck_id, user))


@router.patch("/decks/{deck_id}")
def rename_deck(deck_id: int, data: DeckPatch, user: User = Depends(require_user), db: Session = Depends(get_write_db)):
    deck = require(db, Deck, deck_id, user)
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, 'Choose a title or visibility to update.')
    if changes.get('visibility') in {'public','unlisted'}:
        try:
            no_urls(changes.get('title', deck.title))
            for card in db.scalars(select(Flashcard).where(Flashcard.deck_id == deck.id)):
                no_urls(card.front)
                no_urls(card.back)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        if not deck.share_token:
            deck.share_token = secrets.token_urlsafe(32)
    for key,value in changes.items():
        setattr(deck, key, value)
    deck.updated_at = utcnow()
    db.flush()
    return deck_view(db, deck)


@router.delete("/decks/{deck_id}", status_code=204)
def delete_deck(deck_id: int, user: User = Depends(require_user), db: Session = Depends(get_write_db)):
    db.delete(require(db, Deck, deck_id, user))
    db.flush()
    return Response(status_code=204)


@router.get("/decks/{deck_id}/cards")
def list_cards(deck_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    require(db, Deck, deck_id, user)
    return [card_view(card) for card in db.scalars(owned_query(Flashcard, user).where(Flashcard.deck_id == deck_id).order_by(Flashcard.id))]


@router.post("/decks/{deck_id}/cards", status_code=201)
def add_card(deck_id: int, data: CardInput, user: User = Depends(require_user), db: Session = Depends(get_write_db)):
    deck = require(db, Deck, deck_id, user)
    count = db.scalar(select(func.count()).select_from(Flashcard).join(Deck, Flashcard.deck_id == Deck.id).where(
        Flashcard.deck_id == deck_id, Deck.owner_id == user.id))
    if count >= 150:
        raise HTTPException(409, "This deck has reached its limit of 150 flashcards.")
    card = Flashcard(deck_id=deck_id, **data.model_dump())
    db.add(card)
    deck.updated_at = utcnow()
    db.flush()
    return card_view(card)


@router.get("/cards/recent")
def recent_cards(limit: int = Query(default=12, ge=1, le=30), user: User = Depends(require_user),
                 db: Session = Depends(get_db)):
    rows = db.execute(select(Flashcard, Deck.title).join(Deck, Flashcard.deck_id == Deck.id).where(
        Deck.owner_id == user.id).order_by(Flashcard.created_at.desc(), Flashcard.id.desc()).limit(limit))
    return [{**card_view(card), 'deck_title':title} for card, title in rows]


@router.get("/cards/{card_id}")
def get_card(card_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    return card_view(require(db, Flashcard, card_id, user))


@router.patch("/cards/{card_id}")
def edit_card(card_id: int, data: CardPatch, user: User = Depends(require_user), db: Session = Depends(get_write_db)):
    card = require(db, Flashcard, card_id, user)
    merged = {"card_type": card.card_type, "front": card.front, "back": card.back,
              "front_image":card.front_image, "back_image":card.back_image}
    merged.update(data.model_dump(exclude_unset=True))
    try:
        validated = CardInput(**merged)
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    for key, value in validated.model_dump().items():
        setattr(card, key, value)
    card.updated_at = utcnow()
    require(db, Deck, card.deck_id, user).updated_at = utcnow()
    db.flush()
    return card_view(card)


@router.delete("/cards/{card_id}", status_code=204)
def delete_card(card_id: int, user: User = Depends(require_user), db: Session = Depends(get_write_db)):
    card = require(db, Flashcard, card_id, user)
    require(db, Deck, card.deck_id, user).updated_at = utcnow()
    db.delete(card)
    db.flush()
    return Response(status_code=204)


@router.get("/decks/{deck_id}/sessions")
def session_history(deck_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    require(db, Deck, deck_id, user)
    sessions = db.scalars(owned_query(StudySession, user).where(StudySession.deck_id == deck_id).order_by(StudySession.started_at.desc()).limit(50))
    return [summary_view(db, session) for session in sessions]
