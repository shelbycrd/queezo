"""Ownership scopes shared by flashcard CRUD and internal services."""

from sqlalchemy import select

from app.models import Deck, Flashcard


def owned_flashcards(user_id: int):
    return select(Flashcard).join(Deck, Flashcard.deck_id == Deck.id).where(Deck.owner_id == user_id)
