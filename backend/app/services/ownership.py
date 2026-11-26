"""Ownership scopes shared by flashcard CRUD and internal services."""

from fastapi import HTTPException
from sqlalchemy import select

from app.models import Deck, Flashcard


def owned_flashcards(user_id: int):
    return select(Flashcard).join(Deck, Flashcard.deck_id == Deck.id).where(Deck.owner_id == user_id)


def shared_deck(db, token):
    deck = db.scalar(select(Deck).where(
        Deck.share_token == token, Deck.owner_id.is_not(None), Deck.unpublished_at.is_(None),
        Deck.visibility.in_(('public', 'unlisted')),
    ))
    if deck is None:
        raise HTTPException(404, 'Shared deck not found.')
    return deck
