"""Persistent, owner-scoped distractors for cards explicitly requested by a caller."""

import asyncio
import hashlib
import json
from weakref import WeakValueDictionary

from fastapi import HTTPException
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from app.database import SessionLocal
from app.models import Flashcard, FlashcardDistractorCache, User
from app.services import distractors
from app.services.ownership import owned_flashcards


# Coalesce requests on the same event loop. SQLite arbitrates across workers.
_generation_locks = WeakValueDictionary()


def _fingerprint(front: str, back: str) -> str:
    content = json.dumps([front, back], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _owned_card_and_cache(db, card_id: int, user_id: int):
    row = db.execute(
        owned_flashcards(user_id)
        .with_only_columns(Flashcard.front, Flashcard.back, FlashcardDistractorCache)
        .outerjoin_from(Flashcard, FlashcardDistractorCache,
                        FlashcardDistractorCache.flashcard_id == Flashcard.id)
        .where(Flashcard.id == card_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "Flashcard not found.")
    return row


def _valid_choices(choices, back: str) -> bool:
    if not isinstance(choices, list) or len(choices) != 3:
        return False
    seen = {distractors.comparison_key(back)}
    for choice in choices:
        if not isinstance(choice, str):
            return False
        key = distractors.comparison_key(choice)
        if not key or key in seen:
            return False
        seen.add(key)
    return True


def _cached_choices(row, fingerprint: str, model: str, version: int, back: str):
    if (row is not None
            and row.content_fingerprint == fingerprint
            and row.ollama_model == model
            and row.generation_version == version
            and _valid_choices(row.distractors, back)):
        return row.distractors
    return None


def _lookup(card_id: int, user_id: int, model: str, version: int):
    with SessionLocal() as db:
        front, back, row = _owned_card_and_cache(db, card_id, user_id)
        fingerprint = _fingerprint(front, back)
        return front, back, fingerprint, _cached_choices(row, fingerprint, model, version, back)


def _store(card_id: int, user_id: int, fingerprint: str, model: str, version: int, choices: list[str]):
    with SessionLocal.begin() as db:
        # Recheck the authorized card and any winning write under SQLite's write lock.
        db.execute(text("BEGIN IMMEDIATE"))
        front, back, row = _owned_card_and_cache(db, card_id, user_id)
        if _fingerprint(front, back) != fingerprint:
            raise HTTPException(409, "Flashcard changed while generating distractors. Try again.")
        cached = _cached_choices(row, fingerprint, model, version, back)
        if cached is not None:
            return cached
        if row is None:
            row = FlashcardDistractorCache(flashcard_id=card_id)
            db.add(row)
        row.content_fingerprint = fingerprint
        row.ollama_model = model
        row.generation_version = version
        row.distractors = choices
    return choices


async def get_or_generate_distractors(
    card_id: int, user: User, *, expected_content: tuple[str, str] | None = None,
) -> list[str]:
    """Load or generate choices for a card owned by the authenticated user.

    Database sessions are short-lived and never held open during inference.
    """
    if user is None or user.id is None:
        raise HTTPException(401, "Please log in to continue.")
    user_id = user.id
    lock_key = (asyncio.get_running_loop(), user_id, card_id)
    lock = _generation_locks.setdefault(lock_key, asyncio.Lock())
    async with lock:
        model = distractors.configured_model()
        version = distractors.GENERATION_VERSION
        front, back, fingerprint, cached = await run_in_threadpool(_lookup, card_id, user_id, model, version)
        if expected_content is not None and (front, back) != expected_content:
            raise HTTPException(409, "Flashcard changed while preparing distractors. Try again.")
        if cached is not None:
            return cached
        choices = await distractors.generate_distractors(front, back, model=model)
        if not _valid_choices(choices, back):
            raise distractors.DistractorGenerationError("Ollama returned invalid distractors.")
        return await run_in_threadpool(_store, card_id, user_id, fingerprint, model, version, choices)
