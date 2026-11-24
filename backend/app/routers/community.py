"""Shared read access never broadens owner-only editing or study history."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from pydantic import ValidationError
from app.auth.dependencies import require_user
from app.database import get_db, get_write_db
from app.models import Deck, Flashcard, User
from app.schemas import CardInput
from app.services.content_policy import no_urls
from app.services import limits
from app.services.ownership import shared_deck
from app.services.presenters import card_view, deck_view

router = APIRouter(prefix='/api', tags=['Community decks'])


def shared_view(db, deck):
    view = deck_view(db, deck)
    return {key:view[key] for key in ('title','card_count','visibility','share_token','created_at','updated_at')}


@router.get('/community/decks')
def community(user: User = Depends(require_user), db: Session = Depends(get_db)):
    decks = db.scalars(select(Deck).where(Deck.visibility == 'public', Deck.owner_id.is_not(None),
                        Deck.share_token.is_not(None)).order_by(Deck.created_at.desc(),Deck.id.desc()).limit(20))
    return [shared_view(db, deck) for deck in decks]


@router.get('/shared/decks/{token}')
def read_shared(token: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    deck = shared_deck(db, token)
    cards = db.scalars(select(Flashcard).where(Flashcard.deck_id == deck.id).order_by(Flashcard.id))
    # Shared responses expose content, never internal owners, card IDs or history.
    return {**shared_view(db,deck), 'cards':[{key:value for key,value in card_view(card).items()
            if key not in {'id','deck_id'}} for card in cards]}


@router.post('/shared/decks/{token}/copy', status_code=201)
def copy_shared(token: str, user: User = Depends(require_user), db: Session = Depends(get_write_db, scope="function")):
    source = shared_deck(db, token)
    limits.require_deck_slot(db, user.id)
    limits.require_operation_budget(db, user.id, 'deck-copy', limits.MAX_DECK_COPIES_PER_WINDOW)
    count = db.scalar(select(func.count()).select_from(Flashcard).where(Flashcard.deck_id == source.id))
    if count > limits.MAX_CARDS:
        raise HTTPException(409, 'This deck contains too many cards to copy.')
    limits.require_card_media(db, user.id, None, limits.deck_media(db, source.id))
    try:
        no_urls(source.title)
        cards = [CardInput(card_type=card.card_type,front=card.front,back=card.back,
                    front_image=card.front_image,back_image=card.back_image) for card in
                    db.scalars(select(Flashcard).where(Flashcard.deck_id == source.id).order_by(Flashcard.id))]
    except (ValueError, ValidationError) as error:
        raise HTTPException(422, 'This deck contains unsupported content. Its owner must remove URL links or repair invalid cards before it can be copied.') from error
    deck = Deck(title=source.title, owner_id=user.id, visibility='private')
    db.add(deck)
    db.flush()
    db.add_all([Flashcard(deck_id=deck.id,**card.model_dump()) for card in cards])
    db.flush()
    return deck_view(db,deck)
