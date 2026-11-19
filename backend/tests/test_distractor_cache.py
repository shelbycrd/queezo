import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import AsyncMock

import httpx
from fastapi import HTTPException
import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.orm import sessionmaker

from app.database import init_database, make_engine
from app.models import Deck, Flashcard, FlashcardDistractorCache, FlashcardDistractorSource, User
from app.services import distractor_cache, distractors
from app.services.distractors import DistractorGenerationError
from conftest import deck, review


FIRST_CHOICES = ["Kyoto", "Osaka", "Nara"]
OTHER_CHOICES = ["Nagoya", "Sapporo", "Kobe"]


@pytest.fixture
def cache(client, monkeypatch):
    monkeypatch.setattr(distractor_cache, "SessionLocal", client.factory)
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:1.7b")
    with client.factory() as db:
        owner = db.get(User, client.test_user_id)
    return client, owner


def make_card(client, deck_id, back="Tokyo"):
    response = client.post(f"/api/decks/{deck_id}/cards", json={
        "front": "What is the capital of Japan?", "back": back,
    })
    assert response.status_code == 201
    return response.json()["id"]


def lookup(card_id, user):
    return asyncio.run(distractor_cache.get_or_generate_distractors(card_id, user))


def cached_rows(client):
    with client.factory() as db:
        return list(db.scalars(select(FlashcardDistractorCache).order_by(FlashcardDistractorCache.flashcard_id)))


def test_miss_then_hit_with_reopened_database(cache, monkeypatch):
    client, owner = cache
    generate = AsyncMock(return_value=FIRST_CHOICES)
    monkeypatch.setattr(distractors, "generate_distractors", generate)
    card_id = make_card(client, deck(client, count=0))
    assert cached_rows(client) == []
    generate.assert_not_awaited()

    assert lookup(card_id, owner) == FIRST_CHOICES
    [row] = cached_rows(client)
    assert row.flashcard_id == card_id
    assert row.distractors == FIRST_CHOICES
    assert len(row.content_fingerprint) == 64
    assert row.ollama_model == "qwen3:1.7b"
    assert row.generation_version == distractors.GENERATION_VERSION
    assert row.created_at and row.updated_at
    generate.assert_awaited_once_with("What is the capital of Japan?", "Tokyo", model="qwen3:1.7b")

    engine = make_engine(client.database_url)
    try:
        monkeypatch.setattr(distractor_cache, "SessionLocal", sessionmaker(bind=engine))
        assert lookup(card_id, owner) == FIRST_CHOICES
    finally:
        engine.dispose()
    generate.assert_awaited_once()
    assert cached_rows(client)[0].updated_at == row.updated_at


@pytest.mark.parametrize("changes", [
    {"front": "Which city is Japan’s capital?"},
    {"back": "Tokyo, Japan"},
])
def test_edit_invalidates_only_the_changed_card(cache, monkeypatch, changes):
    client, owner = cache
    deck_id = deck(client, count=0)
    changed, unaffected = [make_card(client, deck_id) for _ in range(2)]
    generate = AsyncMock(side_effect=[FIRST_CHOICES, FIRST_CHOICES, OTHER_CHOICES])
    monkeypatch.setattr(distractors, "generate_distractors", generate)
    lookup(changed, owner)
    lookup(unaffected, owner)
    before = cached_rows(client)[0].content_fingerprint
    assert client.patch(f"/api/cards/{changed}", json=changes).status_code == 200
    assert [row.flashcard_id for row in cached_rows(client)] == [unaffected]
    assert lookup(unaffected, owner) == FIRST_CHOICES
    assert lookup(changed, owner) == OTHER_CHOICES
    assert cached_rows(client)[0].content_fingerprint != before
    assert generate.await_count == 3


def test_noop_text_edit_keeps_cache(cache, monkeypatch):
    client, owner = cache
    card_id = make_card(client, deck(client, count=0))
    generate = AsyncMock(return_value=FIRST_CHOICES)
    monkeypatch.setattr(distractors, "generate_distractors", generate)
    lookup(card_id, owner)
    assert client.patch(f"/api/cards/{card_id}", json={"back": "Tokyo"}).status_code == 200
    assert lookup(card_id, owner) == FIRST_CHOICES
    generate.assert_awaited_once()


@pytest.mark.parametrize("setting", ["model", "version"])
def test_generation_settings_invalidate_existing_entry(cache, monkeypatch, setting):
    client, owner = cache
    card_id = make_card(client, deck(client, count=0))
    generate = AsyncMock(side_effect=[FIRST_CHOICES, OTHER_CHOICES])
    monkeypatch.setattr(distractors, "generate_distractors", generate)
    lookup(card_id, owner)
    [before] = cached_rows(client)

    if setting == "model":
        monkeypatch.setenv("OLLAMA_MODEL", "qwen3:alternate")
    else:
        monkeypatch.setattr(distractors, "GENERATION_VERSION", before.generation_version + 1)
    assert lookup(card_id, owner) == OTHER_CHOICES
    assert lookup(card_id, owner) == OTHER_CHOICES
    assert generate.await_count == 2
    assert generate.await_args.kwargs["model"] == distractors.configured_model()
    [after] = cached_rows(client)
    assert after.content_fingerprint == before.content_fingerprint
    assert after.created_at == before.created_at
    assert after.updated_at > before.updated_at
    assert after.ollama_model == distractors.configured_model()
    assert after.generation_version == distractors.GENERATION_VERSION


@pytest.mark.parametrize("delete_deck", [False, True])
def test_delete_cascades_to_cache(cache, monkeypatch, delete_deck):
    client, owner = cache
    deck_id = deck(client, count=0)
    card_id = make_card(client, deck_id)
    generate = AsyncMock(return_value=FIRST_CHOICES)
    monkeypatch.setattr(distractors, "generate_distractors", generate)
    lookup(card_id, owner)
    path = f"/api/decks/{deck_id}" if delete_deck else f"/api/cards/{card_id}"
    assert client.delete(path).status_code == 204
    assert cached_rows(client) == []
    with pytest.raises(HTTPException) as error:
        lookup(card_id, owner)
    assert error.value.status_code == 404
    generate.assert_awaited_once()


def test_simultaneous_calls_on_one_loop_generate_once(cache, monkeypatch):
    client, owner = cache
    card_id = make_card(client, deck(client, count=0))
    generate = AsyncMock(return_value=FIRST_CHOICES)
    monkeypatch.setattr(distractors, "generate_distractors", generate)

    async def run():
        first, second = await asyncio.gather(
            distractor_cache.get_or_generate_distractors(card_id, owner),
            distractor_cache.get_or_generate_distractors(card_id, owner),
        )
        assert first == second == FIRST_CHOICES

    asyncio.run(run())
    generate.assert_awaited_once()
    assert len(cached_rows(client)) == 1


def test_competing_event_loops_reuse_the_winning_write(cache, monkeypatch):
    client, owner = cache
    card_id = make_card(client, deck(client, count=0))
    barrier = Barrier(2)

    async def generate(*args, **kwargs):
        slot = await asyncio.to_thread(barrier.wait, 10)
        return FIRST_CHOICES if slot == 0 else OTHER_CHOICES

    monkeypatch.setattr(distractors, "generate_distractors", generate)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(lookup, card_id, owner) for _ in range(2)]
        first, second = [result.result(timeout=15) for result in results]
    [row] = cached_rows(client)
    assert first == second == row.distractors
    assert first in (FIRST_CHOICES, OTHER_CHOICES)


@pytest.mark.parametrize("change,status", [("edit", 409), ("delete", 404), ("transfer", 404)])
def test_card_changes_during_inference_cannot_leave_stale_choices(cache, monkeypatch, change, status):
    client, owner = cache
    deck_id = deck(client, count=0)
    card_id = make_card(client, deck_id)

    async def generate(*args, **kwargs):
        if change == "edit":
            assert client.patch(f"/api/cards/{card_id}", json={"back": "Tokyo, Japan"}).status_code == 200
        elif change == "delete":
            assert client.delete(f"/api/cards/{card_id}").status_code == 204
        else:
            with client.factory.begin() as db:
                db.get(Deck, deck_id).owner_id = None
        return FIRST_CHOICES

    monkeypatch.setattr(distractors, "generate_distractors", generate)
    with pytest.raises(HTTPException) as error:
        lookup(card_id, owner)
    assert error.value.status_code == status
    assert cached_rows(client) == []


@pytest.mark.parametrize("choices", [
    ["Kyoto", "Osaka"],
    ["Kyoto", "Osaka", " tokyo "],
    ["Kyoto", " kYoTo ", "Osaka"],
    ["Kyoto", "Osaka", None],
    ["Kyoto", "Osaka", "  "],
])
def test_malformed_generation_is_never_cached(cache, monkeypatch, choices):
    client, owner = cache
    card_id = make_card(client, deck(client, count=0))
    monkeypatch.setattr(distractors, "generate_distractors", AsyncMock(return_value=choices))
    with pytest.raises(DistractorGenerationError):
        lookup(card_id, owner)
    assert cached_rows(client) == []


def test_failure_leaves_no_cache_and_next_call_can_recover(cache, monkeypatch):
    client, owner = cache
    card_id = make_card(client, deck(client, count=0))
    generate = AsyncMock(side_effect=[DistractorGenerationError("Ollama unavailable"), FIRST_CHOICES])
    monkeypatch.setattr(distractors, "generate_distractors", generate)
    with pytest.raises(distractor_cache.InsufficientDistractorsError):
        lookup(card_id, owner)
    assert cached_rows(client) == []
    assert lookup(card_id, owner) == FIRST_CHOICES
    assert len(cached_rows(client)) == 1


def test_invalid_saved_distractors_are_replaced(cache, monkeypatch):
    client, owner = cache
    card_id = make_card(client, deck(client, count=0))
    monkeypatch.setattr(distractors, "generate_distractors", AsyncMock(side_effect=[FIRST_CHOICES, OTHER_CHOICES]))
    lookup(card_id, owner)
    with client.factory.begin() as db:
        db.get(FlashcardDistractorCache, card_id).distractors = ["Kyoto", "kyoto", "Tokyo"]
    assert lookup(card_id, owner) == OTHER_CHOICES
    assert cached_rows(client)[0].distractors == OTHER_CHOICES


def test_nonowners_cannot_hit_cache_or_trigger_generation(cache, monkeypatch):
    client, owner = cache
    deck_id = deck(client, count=0)
    cached, uncached = [make_card(client, deck_id) for _ in range(2)]
    with client.factory.begin() as db:
        outsider = User(email="outsider@example.com", password_hash="unused")
        db.add(outsider)

    generate = AsyncMock(return_value=FIRST_CHOICES)
    monkeypatch.setattr(distractors, "generate_distractors", generate)
    lookup(cached, owner)
    for card_id in (cached, uncached):
        with pytest.raises(HTTPException) as error:
            lookup(card_id, outsider)
        assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        lookup(cached, None)
    assert error.value.status_code == 401
    assert [row.flashcard_id for row in cached_rows(client)] == [cached]
    generate.assert_awaited_once()


def test_startup_adds_cache_to_existing_database_and_preserves_study_history(cache):
    client, _ = cache
    deck_id = deck(client)
    session = client.post(f"/api/decks/{deck_id}/study")
    assert session.status_code == 201
    review(client, session.json())
    engine = client.factory.kw["bind"]
    history_tables = ("flashcards", "study_sessions", "study_session_cards", "study_reviews")

    def read_history(connection):
        return [connection.execute(text(f"SELECT * FROM {table}")).all() for table in history_tables]

    with engine.begin() as db:
        before = read_history(db)
        assert all(before)
        # Simulate a database initialized by the release before this cache existed.
        db.execute(text("DROP TRIGGER flashcard_distractors_invalidate"))
        db.execute(text("DROP TRIGGER flashcard_distractor_source_update"))
        db.execute(text("DROP TRIGGER flashcard_distractor_source_delete"))
        db.execute(text("DROP TABLE flashcard_distractor_sources"))
        db.execute(text("DROP TABLE flashcard_distractor_cache"))
    init_database(engine)
    init_database(engine)
    with engine.begin() as db:
        assert read_history(db) == before
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []
    assert cached_rows(client) == []


def source_rows(client, target):
    with client.factory() as db:
        return db.scalars(select(FlashcardDistractorSource).where(
            FlashcardDistractorSource.flashcard_id == target,
        ).order_by(FlashcardDistractorSource.position)).all()


@pytest.mark.parametrize("ai_count", [0, 1, 2, 3])
def test_ai_and_deck_choices_are_cached_with_source_provenance(cache, monkeypatch, ai_count):
    client, owner = cache
    deck_id = deck(client, count=0)
    target = make_card(client, deck_id)
    pool = OTHER_CHOICES[:3 - ai_count]
    source_ids = {answer: make_card(client, deck_id, answer) for answer in pool}
    ai = FIRST_CHOICES[:ai_count]
    requests = []
    generate = distractors.generate_distractors

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={
            "message": {"content": json.dumps({"distractors": [" TOKYO ", *ai, "", None]})},
        })

    async def generate_mocked(front, back, *, model):
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            return await generate(front, back, client=http, model=model)

    monkeypatch.setattr(distractors, "generate_distractors", generate_mocked)
    choices = lookup(target, owner)
    assert len(choices) == len(set(choices)) == 3
    assert set(choices[:ai_count]) == set(ai)
    assert set(choices[ai_count:]) <= set(pool)

    sources = source_rows(client, target)
    assert [source.position for source in sources] == list(range(ai_count, 3))
    for source in sources:
        answer = choices[source.position]
        assert source.source_card_id == source_ids[answer]
        assert source.content_fingerprint == distractor_cache._fingerprint("What is the capital of Japan?", answer)
    assert lookup(target, owner) == choices
    assert len(requests) == (1 if ai_count == 3 else 3)


@pytest.mark.parametrize("has_alternatives", [False, True])
def test_insufficient_unique_same_deck_backs_do_not_borrow_from_other_decks(cache, monkeypatch, has_alternatives):
    client, owner = cache
    deck_id = deck(client, count=0)
    target = make_card(client, deck_id)
    other_deck = deck(client, count=0)
    for answer in OTHER_CHOICES:
        make_card(client, other_deck, answer)
    with client.factory.begin() as db:
        outsider = User(email="other@example.com", password_hash="unused")
        db.add(outsider)
        db.flush()
        private = Deck(owner_id=outsider.id, title="Other user's deck")
        db.add(private)
        db.flush()
        db.add_all([Flashcard(deck_id=private.id, front="Question", back=answer) for answer in FIRST_CHOICES])
        if has_alternatives:
            db.add_all([Flashcard(deck_id=deck_id, front="Question", back=answer)
                        for answer in ("ToKyO", " Kyoto Station ", "KYOTO \tstation", "\t")])
    generate = AsyncMock(side_effect=DistractorGenerationError("Could not reach Ollama"))
    monkeypatch.setattr(distractors, "generate_distractors", generate)
    with pytest.raises(distractor_cache.InsufficientDistractorsError):
        lookup(target, owner)
    with pytest.raises(HTTPException) as error:
        lookup(target, outsider)
    assert error.value.status_code == 404
    assert cached_rows(client) == []
    generate.assert_awaited_once()


def test_fallback_skips_equivalent_deck_and_ai_choices(cache, monkeypatch):
    client, owner = cache
    deck_id = deck(client, count=0)
    target = make_card(client, deck_id)
    for answer in ("tOkYo", "KYOTO\tSTATION", "Kobe", "KOBE", "Nara", "nAra"):
        make_card(client, deck_id, answer)
    generate = AsyncMock(side_effect=DistractorGenerationError("Partial", candidates=["Kyoto Station"]))
    monkeypatch.setattr(distractors, "generate_distractors", generate)
    assert {distractors.comparison_key(choice) for choice in lookup(target, owner)} == {
        "kyoto station", "kobe", "nara",
    }


@pytest.mark.parametrize("change", ["front", "back", "delete", "move"])
def test_source_changes_invalidate_only_dependent_caches(cache, monkeypatch, change):
    client, owner = cache
    deck_id = deck(client, count=0)
    target = make_card(client, deck_id)
    other = make_card(client, deck(client, count=0))
    replacement_deck = deck(client, count=0)
    sources = [make_card(client, deck_id, answer) for answer in OTHER_CHOICES]
    source = sources[0]

    async def generate(front, back, *, model):
        raise DistractorGenerationError("Could not reach Ollama")

    monkeypatch.setattr(
        distractors, "generate_distractors",
        AsyncMock(side_effect=[FIRST_CHOICES, DistractorGenerationError("Unavailable")]),
    )
    assert lookup(other, owner) == FIRST_CHOICES
    assert set(lookup(target, owner)) == set(OTHER_CHOICES)
    assert client.patch(f"/api/cards/{source}", json={"back": OTHER_CHOICES[0]}).status_code == 200
    assert {row.flashcard_id for row in cached_rows(client)} == {target, other}
    if change == "delete":
        assert client.delete(f"/api/cards/{source}").status_code == 204
    elif change == "move":
        with client.factory.begin() as db:
            db.get(Flashcard, source).deck_id = replacement_deck
    else:
        assert client.patch(f"/api/cards/{source}", json={change: "New text"}).status_code == 200
    assert [row.flashcard_id for row in cached_rows(client)] == [other]
    assert source_rows(client, target) == []

    monkeypatch.setattr(distractors, "generate_distractors", generate)
    assert lookup(other, owner) == FIRST_CHOICES
    if change in {"delete", "move"}:
        with pytest.raises(DistractorGenerationError):
            lookup(target, owner)
        make_card(client, deck_id, "New text")
    choices = lookup(target, owner)
    expected = set(OTHER_CHOICES) if change == "front" else {*OTHER_CHOICES[1:], "New text"}
    assert set(choices) == expected


def test_hybrid_cache_replaced_cleanly_when_generation_version_changes(cache, monkeypatch):
    client, owner = cache
    deck_id = deck(client, count=4)
    target = make_card(client, deck_id)
    generate = AsyncMock(side_effect=[DistractorGenerationError("Unavailable"), FIRST_CHOICES])
    monkeypatch.setattr(distractors, "generate_distractors", generate)
    assert len(lookup(target, owner)) == 3
    assert len(source_rows(client, target)) == 3
    monkeypatch.setattr(distractors, "GENERATION_VERSION", distractors.GENERATION_VERSION + 1)
    assert lookup(target, owner) == FIRST_CHOICES
    assert source_rows(client, target) == []


def test_hybrid_racing_writers_share_choices_and_provenance(cache, monkeypatch):
    client, owner = cache
    target = make_card(client, deck(client, count=4))
    barrier = Barrier(2)

    async def generate(*args, **kwargs):
        slot = await asyncio.to_thread(barrier.wait, 10)
        raise DistractorGenerationError("Partial", candidates=[FIRST_CHOICES[slot]])

    monkeypatch.setattr(distractors, "generate_distractors", generate)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(lookup, target, owner) for _ in range(2)]
        first, second = [result.result(timeout=15) for result in results]
    [row] = cached_rows(client)
    assert first == second == row.distractors
    assert first[0] in FIRST_CHOICES[:2]
    assert len(source_rows(client, target)) == 2


def test_startup_preserves_a_pre_hybrid_ai_cache(cache, monkeypatch):
    client, owner = cache
    target = make_card(client, deck(client, count=0))
    generate = AsyncMock(return_value=FIRST_CHOICES)
    monkeypatch.setattr(distractors, "generate_distractors", generate)
    lookup(target, owner)
    engine = client.factory.kw["bind"]
    with engine.begin() as db:
        db.execute(text("DROP TRIGGER flashcard_distractor_source_update"))
        db.execute(text("DROP TRIGGER flashcard_distractor_source_delete"))
        db.execute(text("DROP TABLE flashcard_distractor_sources"))
        before = db.execute(text("SELECT * FROM flashcard_distractor_cache")).all()
    init_database(engine)
    init_database(engine)
    with engine.begin() as db:
        assert db.execute(text("SELECT * FROM flashcard_distractor_cache")).all() == before
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []
    assert lookup(target, owner) == FIRST_CHOICES
    generate.assert_awaited_once()
