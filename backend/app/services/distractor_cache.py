"""Persistent, owner-scoped distractors for cards explicitly requested by a caller."""

import asyncio
import hashlib
import json
import random
from collections import defaultdict
from contextlib import nullcontext
from weakref import WeakValueDictionary

from fastapi import HTTPException
from sqlalchemy import and_, delete, select, text
from starlette.concurrency import run_in_threadpool

from app.database import SessionLocal
from app.models import Flashcard, FlashcardDistractorCache, FlashcardDistractorSource, User
from app.services import distractors
from app.services.ownership import owned_flashcards


# Coalesce requests on the same event loop. SQLite arbitrates across workers.
_generation_locks = WeakValueDictionary()


class InsufficientDistractorsError(distractors.DistractorGenerationError):
    """The model and the authorized deck together supplied fewer than three distractors."""


def _fingerprint(front: str, back: str) -> str:
    content = json.dumps([front, back], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _owned_card_and_cache(db, card_id: int, user_id: int):
    row = db.execute(
        owned_flashcards(user_id)
        .with_only_columns(Flashcard.front, Flashcard.back, Flashcard.deck_id, FlashcardDistractorCache)
        .outerjoin_from(Flashcard, FlashcardDistractorCache,
                        FlashcardDistractorCache.flashcard_id == Flashcard.id)
        .where(Flashcard.id == card_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "Flashcard not found.")
    return row


def _valid_choices(choices, back: str, count: int = 3) -> bool:
    if not isinstance(choices, list) or len(choices) != count:
        return False
    seen = {distractors.comparison_key(back)}
    for choice in choices:
        if not isinstance(choice, str) or distractors.has_invalid_unicode(choice):
            return False
        key = distractors.comparison_key(choice)
        if not key or key in seen:
            return False
        seen.add(key)
    return True


def _cache_matches(row, fingerprint: str, model: str, version: int, back: str):
    return (row.content_fingerprint == fingerprint and row.ollama_model == model
            and row.generation_version == version and _valid_choices(row.distractors, back))


def _cache_sources(db, card_ids, deck_id: int):
    return db.execute(
        select(FlashcardDistractorSource, Flashcard.deck_id, Flashcard.front, Flashcard.back)
        .outerjoin(Flashcard, and_(Flashcard.id == FlashcardDistractorSource.source_card_id,
                                   Flashcard.deck_id == deck_id))
        .where(FlashcardDistractorSource.flashcard_id.in_(card_ids))
    )


def _sources_match(row, sources, deck_id: int):
    return all(
        source_deck == deck_id and source.content_fingerprint == _fingerprint(source_front, source_back)
        and row.distractors[source.position] == source_back.strip()
        for source, source_deck, source_front, source_back in sources
    )


def _cached_choices(db, row, fingerprint: str, model: str, version: int, deck_id: int, back: str):
    if (row is not None and _cache_matches(row, fingerprint, model, version, back)
            and _sources_match(row, _cache_sources(db, [row.flashcard_id], deck_id), deck_id)):
        return row.distractors
    return None


def cached_choices_for_deck(db, deck_id: int, cards: dict[int, Flashcard]) -> dict[int, list[str]]:
    """Read caches for cards already authorized in the caller's transaction."""
    if not cards:
        return {}
    model, version = distractors.configured_model(), distractors.GENERATION_VERSION
    rows = db.scalars(select(FlashcardDistractorCache).where(FlashcardDistractorCache.flashcard_id.in_(cards)))
    matches = {}
    for row in rows:
        card = cards[row.flashcard_id]
        if _cache_matches(row, _fingerprint(card.front, card.back), model, version, card.back):
            matches[row.flashcard_id] = row
    if not matches:
        return {}
    sources = defaultdict(list)
    for provenance in _cache_sources(db, matches, deck_id):
        sources[provenance[0].flashcard_id].append(provenance)
    return {
        card_id: row.distractors for card_id, row in matches.items()
        if _sources_match(row, sources.get(card_id, ()), deck_id)
    }


def _lookup(card_id: int, user_id: int, model: str, version: int):
    with SessionLocal() as db:
        # Read the cache and its provenance from the same SQLite snapshot.
        db.execute(text("BEGIN"))
        front, back, deck_id, row = _owned_card_and_cache(db, card_id, user_id)
        fingerprint = _fingerprint(front, back)
        return front, back, fingerprint, _cached_choices(db, row, fingerprint, model, version, deck_id, back)


def _deck_choices(db, deck_id, card_id, back, ai_choices):
    seen = {distractors.comparison_key(choice) for choice in [back, *ai_choices]}
    cards = db.execute(select(Flashcard.id, Flashcard.front, Flashcard.back).where(
        Flashcard.deck_id == deck_id, Flashcard.id != card_id,
    )).all()
    random.shuffle(cards)
    selected = []
    needed = 3 - len(ai_choices)
    for source_id, source_front, source_back in cards:
        key = distractors.comparison_key(source_back)
        if key and key not in seen:
            seen.add(key)
            selected.append((source_id, _fingerprint(source_front, source_back), source_back.strip()))
            if len(selected) == needed:
                return selected
    return []


def _store(card_id, user_id, fingerprint, model, version, choices, failure_reason):
    with SessionLocal.begin() as db:
        # Recheck the authorized card and any winning write under SQLite's write lock.
        db.execute(text("BEGIN IMMEDIATE"))
        front, back, deck_id, row = _owned_card_and_cache(db, card_id, user_id)
        if _fingerprint(front, back) != fingerprint:
            raise HTTPException(409, "Flashcard changed while generating distractors. Try again.")
        cached = _cached_choices(db, row, fingerprint, model, version, deck_id, back)
        if cached is not None:
            return cached

        sources = []
        if len(choices) < 3:
            sources = _deck_choices(db, deck_id, card_id, back, choices)
            if not sources:
                raise InsufficientDistractorsError(
                    "Ollama and the deck supplied fewer than three distinct distractors.", reason=failure_reason,
                )

        if row is None:
            row = FlashcardDistractorCache(flashcard_id=card_id)
            db.add(row)
        else:
            db.execute(delete(FlashcardDistractorSource).where(FlashcardDistractorSource.flashcard_id == card_id))
        row.content_fingerprint = fingerprint
        row.ollama_model = model
        row.generation_version = version
        row.distractors = choices + [answer for _, _, answer in sources]
        if sources:
            db.flush()
            db.add_all([
                FlashcardDistractorSource(flashcard_id=card_id, position=position, source_card_id=source_id,
                                          content_fingerprint=source_fingerprint)
                for position, (source_id, source_fingerprint, _) in enumerate(sources, start=len(choices))
            ])
    return row.distractors


async def get_or_generate_distractors(
    card_id: int, user: User, *, expected_content: tuple[str, str] | None = None,
    model_slot: asyncio.Lock | None = None,
) -> list[str]:
    """Load or assemble choices for a card owned by the authenticated user.

    Database sessions are short-lived. The optional shared slot covers only inference.
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
        failure_reason = "insufficient_distractors"
        try:
            async with model_slot if model_slot is not None else nullcontext():
                choices = await distractors.generate_distractors(front, back, model=model)
            if not _valid_choices(choices, back):
                raise distractors.DistractorGenerationError(
                    "Ollama returned invalid distractors.", reason="invalid_ai_response",
                )
        except distractors.DistractorGenerationError as error:
            failure_reason = error.reason
            choices = list(error.candidates)
            if len(choices) >= 3 or not _valid_choices(choices, back, len(choices)):
                choices = []
        return await run_in_threadpool(
            _store, card_id, user_id, fingerprint, model, version, choices, failure_reason,
        )
