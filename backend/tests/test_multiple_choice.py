import asyncio
import json
import socket
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, text

from app.auth.service import create_user
from app.database import init_database
from app.models import (
    Flashcard, FlashcardDistractorCache, FlashcardDistractorSource, MultipleChoiceQuestion, MultipleChoiceSession, User, utcnow,
)
from app.services import distractor_cache, distractors, multiple_choice as study
from app.services.distractors import DistractorGenerationError
from conftest import deck, review

CHOICES = ["Wrong first", "Wrong second", "Wrong third"]


@pytest.fixture
def mc(client, monkeypatch):
    monkeypatch.setattr(distractor_cache, "SessionLocal", client.factory)
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:1.7b")
    return client


def start(client, deck_id):
    response = client.post(f"/api/decks/{deck_id}/multiple-choice")
    assert response.status_code == 202, response.text
    state = response.json()
    assert state["status"] == "preparing"
    return f"/api/multiple-choice/{state['id']}", state


def wait_for_state(client, path, status):
    deadline = monotonic() + 7
    while monotonic() < deadline:
        response = client.get(path)
        assert response.status_code == 200
        if response.json()["status"] == status:
            return response.json()
        sleep(0.02)
    pytest.fail(f"Expected {status}, last response was {response.text}")


def mock_generation(monkeypatch, **kwargs):
    generator = AsyncMock(**kwargs)
    monkeypatch.setattr(distractors, "generate_distractors", generator)
    return generator


def test_cache_hit_shuffled_options_and_grading_survive_source_edits(mc, monkeypatch):
    deck_id = deck(mc, count=2)
    generate = mock_generation(monkeypatch, return_value=CHOICES)
    # Put the correct option last deterministically, without changing Classic randomness.
    monkeypatch.setattr(study, "random", SimpleNamespace(shuffle=lambda items: items.reverse()))
    with mc.factory() as db:
        owner = db.get(User, mc.test_user_id)
        cached_id = db.scalar(select(Flashcard.id).where(Flashcard.deck_id == deck_id).order_by(Flashcard.id))
    asyncio.run(distractor_cache.get_or_generate_distractors(cached_id, owner))
    generate.reset_mock()

    path, initial = start(mc, deck_id)
    assert initial["progress"] == {"total": 2, "completed": 0, "ready": 0, "failed": 0}
    active = wait_for_state(mc, path, "active")
    assert active["progress"] == {"total": 2, "completed": 2, "ready": 2, "failed": 0}
    generate.assert_awaited_once()

    question = mc.get(path + "/question").json()
    assert question == mc.get(path + "/question").json()
    assert set(question) == {"id", "front", "front_image", "options", "eliminated_option_id", "attempts_remaining"}
    assert {option["text"] for option in question["options"]} == {*CHOICES, "Answer 1"}
    assert all(set(option) == {"id", "text"} for option in question["options"])
    assert len({option["id"] for option in question["options"]}) == 4
    assert question["options"][-1]["text"] == "Answer 1"

    original = question["options"][-1]
    with mc.factory() as db:
        source_id = db.scalar(select(Flashcard.id).where(Flashcard.deck_id == deck_id,
                                                        Flashcard.front == question["front"]))
    assert mc.patch(f"/api/cards/{source_id}", json={"back": "Edited after preparation"}).status_code == 200
    assert mc.delete(f"/api/cards/{source_id}").status_code == 204
    assert mc.get(path + "/question").json() == question

    wrong = {"question_id": question["id"], "option_id": question["options"][0]["id"]}
    assert mc.post(path + "/answer", json={**wrong, "is_correct": True}).status_code == 422
    assert mc.post(path + "/answer", json={**wrong, "option_id": str(uuid4())}).status_code == 422
    assert mc.post(path + "/answer", json={**wrong, "question_id": str(uuid4())}).status_code == 409
    retry = mc.post(path + "/answer", json=wrong).json()
    assert retry["retry"] and "correct_option" not in retry and retry["session"]["answered"] == 0
    assert mc.post(path + "/answer", json=wrong).status_code == 409
    wrong["option_id"] = question["options"][1]["id"]
    graded = mc.post(path + "/answer", json=wrong).json()
    assert graded["is_correct"] is False and graded["correct_option"] == original
    assert graded["session"]["answered"] == 1
    assert mc.post(path + "/answer", json=wrong).status_code == 409

    second = mc.get(path + "/question").json()
    last = {"question_id": second["id"], "option_id": second["options"][-1]["id"]}
    assert mc.post(path + "/answer", json={**last, "option_id": original["id"]}).status_code == 422
    result = mc.post(path + "/answer", json=last).json()
    assert result["is_correct"] is True
    assert result["session"]["status"] == "completed"
    assert result["session"]["answered"] == 2 and result["session"]["correct"] == 1
    assert mc.post(path + "/answer", json=last).status_code == 409
    shared_history = mc.get(f"/api/decks/{deck_id}/multiple-choice/sessions").json()
    assert shared_history == [result["session"]]
    assert mc.get(f"/api/decks/{deck_id}/sessions").json() == []
    assert mc.get("/api/dashboard/activity").json()["active_today"] is True


def test_offline_ollama_prepares_and_preserves_deck_answer_snapshots(mc, monkeypatch):
    # A bound, non-listening socket guarantees the connection is refused locally.
    deck_id = deck(mc, count=4)
    with socket.socket() as offline:
        offline.bind(("127.0.0.1", 0))
        monkeypatch.setenv("OLLAMA_BASE_URL", f"http://127.0.0.1:{offline.getsockname()[1]}")
        path, _ = start(mc, deck_id)
        active = wait_for_state(mc, path, "active")
    assert active["progress"] == {"total": 4, "completed": 4, "ready": 4, "failed": 0}
    assert active["failures"] == []

    question = mc.get(path + "/question").json()
    with mc.factory() as db:
        answers = dict(db.execute(select(Flashcard.front, Flashcard.back).where(
            Flashcard.deck_id == deck_id,
        )).all())
        source_id = db.scalar(select(Flashcard.id).where(
            Flashcard.deck_id == deck_id, Flashcard.front != question["front"],
        ).limit(1))
    assert {option["text"] for option in question["options"]} == set(answers.values())
    assert mc.delete(f"/api/cards/{source_id}").status_code == 204
    assert mc.get(path + "/question").json() == question
    correct = next(option for option in question["options"] if option["text"] == answers[question["front"]])
    response = mc.post(path + "/answer", json={"question_id": question["id"], "option_id": correct["id"]})
    assert response.status_code == 200 and response.json()["is_correct"] is True


@pytest.mark.parametrize("has_distinct_ai_choice", [False, True], ids=["shortage", "hybrid-ready"])
def test_deck_with_repeated_back_prepares_only_with_an_additional_distinct_choice(
    mc, monkeypatch, has_distinct_ai_choice,
):
    deck_id = deck(mc, count=0)
    synthetic_cards = {
        20: ("xpqjzs", "Orbit"),
        21: ("Another orbital question", " ORBIT "),
        99: ("What pulls objects toward each other?", "Gravity"),
        100: ("bzzrk", "Mass"),
    }
    with mc.factory.begin() as db:
        db.add_all([
            Flashcard(id=card_id, deck_id=deck_id, front=front, back=back)
            for card_id, (front, back) in synthetic_cards.items()
        ])

    affected = {synthetic_cards[20][0], synthetic_cards[99][0]}
    calls = Counter()
    generate = distractors.generate_distractors

    def respond(request):
        messages = json.loads(request.content)["messages"]
        card = json.loads(messages[-1]["content"])
        front = card["question"]
        calls[front] += 1
        candidates = CHOICES
        if front in affected:
            # "Mass" is a valid partial AI answer for both cards, but also exists in the deck.
            partial = "Inertia" if has_distinct_ai_choice else "Mass"
            if calls[front] == 1:
                correct = card["correct_answer"]
                candidates = [correct, correct.upper(), None, partial, partial.upper(), ""]
            elif calls[front] == 2:
                assert card["previous_candidates"] == [partial]
                return httpx.Response(200, json={"message": {"content": "malformed JSON"}})
            else:
                assert card["previous_candidates"] == [partial]
                error_type = httpx.ReadTimeout if front == synthetic_cards[20][0] else httpx.ConnectError
                raise error_type("Synthetic request failure", request=request)
        return httpx.Response(200, json={"message": {"content": json.dumps({"distractors": candidates})}})

    async def mocked_generation(front, back, *, model):
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            return await generate(front, back, client=http, model=model)

    monkeypatch.setattr(distractors, "generate_distractors", mocked_generation)
    path, started = start(mc, deck_id)
    state = wait_for_state(mc, path, "active" if has_distinct_ai_choice else "failed")
    ready = 4 if has_distinct_ai_choice else 2
    assert state["progress"] == {"total": 4, "completed": 4, "ready": ready, "failed": 4 - ready}
    failures = {item["card_id"]: item["reason"] for item in state["failures"]}
    assert failures == ({} if has_distinct_ai_choice else {20: "generation_timeout", 99: "ollama_unavailable"})
    assert all(calls[front] == 3 for front in affected)

    with mc.factory() as db:
        for card_id in (20, 99):
            cache = db.get(FlashcardDistractorCache, card_id)
            if not has_distinct_ai_choice:
                assert cache is None
                continue
            assert "Inertia" in cache.distractors
            snapshot = db.scalar(select(MultipleChoiceQuestion).where(
                MultipleChoiceQuestion.session_id == started["id"],
                MultipleChoiceQuestion.source_card_id == card_id,
            ))
            assert {distractors.comparison_key(option["text"]) for option in snapshot.options} == {
                "orbit", "gravity", "mass", "inertia",
            }
            correct = next(option["text"] for option in snapshot.options
                           if option["id"] == snapshot.correct_option_id)
            assert correct == synthetic_cards[card_id][1]


def test_reported_keyboard_mash_deck_prepares_with_partial_generation(mc, monkeypatch):
    deck_id = deck(mc, count=0)
    rows = [
        ("awgaw", "asdaw", "asdax"),
        ("awgaa", "awdawd", "awdaed"),
        ("gasdfg", "awdawd", "awdbwd"),
        ("tyjyukyu", "khl", "kll"),
    ]
    with mc.factory.begin() as db:
        db.add_all([Flashcard(deck_id=deck_id, front=front, back=back) for front, back, _ in rows])

    generator = distractors.generate_distractors
    choices_by_front = {front: partial for front, _, partial in rows}
    attempts = Counter()

    def respond(request):
        system, user = json.loads(request.content)["messages"]
        card = json.loads(user["content"])
        front = card["question"]
        attempts[front] += 1
        if attempts[front] == 1:
            content = json.dumps({"distractors": [card["correct_answer"], "An irrelevant phrase"]})
        else:
            assert distractors.STRING_PROMPT in system["content"]
            content = json.dumps({"distractors": [choices_by_front[front]]})
        return httpx.Response(200, json={"message": {"content": content}})

    async def mocked_generation(front, back, *, model):
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            return await generator(front, back, client=http, model=model)

    monkeypatch.setattr(distractors, "generate_distractors", mocked_generation)
    path, _ = start(mc, deck_id)
    state = wait_for_state(mc, path, "active")
    assert state["progress"] == {"total": 4, "completed": 4, "ready": 4, "failed": 0}
    assert set(attempts.values()) == {3}
    with mc.factory() as db:
        for card_id, front in db.execute(select(Flashcard.id, Flashcard.front).where(Flashcard.deck_id == deck_id)):
            cached = db.get(FlashcardDistractorCache, card_id)
            assert len(cached.distractors) == 3
            assert choices_by_front[front] in cached.distractors


def test_unauthenticated_csrf_and_cross_account_requests(mc, monkeypatch):
    deck_id = deck(mc)
    generate = mock_generation(monkeypatch, return_value=CHOICES)
    path, _ = start(mc, deck_id)
    wait_for_state(mc, path, "active")
    question = mc.get(path + "/question").json()
    data = {"question_id": question["id"], "option_id": question["options"][0]["id"]}
    token = mc.headers.pop("X-CSRF-Token")
    assert mc.post(path + "/answer", json=data).status_code == 403
    mc.headers["X-CSRF-Token"] = token
    with mc.factory.begin() as db:
        create_user(db, "outsider@example.com", "separate test passphrase")
    mc.cookies.clear()
    assert mc.get(path).status_code == 401
    assert mc.post(f"/api/decks/{deck_id}/multiple-choice").status_code == 401
    login = mc.post("/api/auth/login", json={
        "email": "outsider@example.com", "password": "separate test passphrase",
    })
    assert login.status_code == 200
    mc.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    assert mc.post(f"/api/decks/{deck_id}/multiple-choice").status_code == 404
    assert mc.get(f"/api/decks/{deck_id}/multiple-choice/sessions").status_code == 404
    assert mc.get(path).status_code == 404
    assert mc.get(path + "/question").status_code == 404
    assert mc.post(path + "/answer", json=data).status_code == 404
    for suffix in ("/cancel", "/retry", "/continue"):
        assert mc.post(path + suffix).status_code == 404
    generate.assert_awaited_once()


def test_empty_deck_returns_conflict_without_creating_session(mc):
    deck_id = deck(mc, count=0)
    assert mc.post(f"/api/decks/{deck_id}/multiple-choice").status_code == 409
    assert mc.get(f"/api/decks/{deck_id}/multiple-choice/sessions").json() == []


def test_generation_progress_and_concurrency_across_decks(mc, monkeypatch):
    first_deck, second_deck = deck(mc, count=2), deck(mc, count=1)
    at_second = Event()
    release = Event()
    calls, active, peak = 0, 0, 0

    async def generate(*args, **kwargs):
        nonlocal calls, active, peak
        calls += 1
        active += 1
        peak = max(peak, active)
        try:
            if calls > 1:
                at_second.set()
                while not release.is_set():
                    await asyncio.sleep(0.01)
            return CHOICES
        finally:
            active -= 1

    monkeypatch.setattr(distractors, "generate_distractors", generate)
    first, _ = start(mc, first_deck)
    assert at_second.wait(5)
    second, _ = start(mc, second_deck)
    try:
        progress = mc.get(first).json()["progress"]
        assert progress == {"total": 2, "completed": 1, "ready": 1, "failed": 0}
        assert mc.get(first + "/question").status_code == 409
        assert mc.get(second).json()["progress"]["completed"] == 0
        assert peak == 1 and calls == 2
    finally:
        release.set()
    wait_for_state(mc, first, "active")
    wait_for_state(mc, second, "active")
    assert calls == 3 and peak == 1


def test_cached_card_commits_first_without_changing_study_order(mc, monkeypatch):
    deck_id = deck(mc, count=2)
    with mc.factory() as db:
        owner = db.get(User, mc.test_user_id)
        first, cached = db.scalars(select(Flashcard).where(Flashcard.deck_id == deck_id)
                                   .order_by(Flashcard.id)).all()
    mock_generation(monkeypatch, return_value=CHOICES)
    asyncio.run(distractor_cache.get_or_generate_distractors(cached.id, owner))
    photo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jSxsAAAAASUVORK5CYII="
    with mc.factory.begin() as db:
        card = db.get(Flashcard, cached.id)
        card.front_image = photo
        card.back_image = photo
    monkeypatch.setattr(study, "random", SimpleNamespace(shuffle=lambda items: None))
    entered, release = Event(), Event()

    async def generate(front, back, *, model):
        assert front == first.front
        entered.set()
        while not release.is_set():
            await asyncio.sleep(0.01)
        return CHOICES

    monkeypatch.setattr(distractors, "generate_distractors", generate)
    path, state = start(mc, deck_id)
    try:
        assert entered.wait(5)
        preparing = mc.get(path).json()
        assert preparing["status"] == "preparing" and preparing["progress"]["ready"] == 1
        assert mc.get(path + "/question").status_code == 409
        with mc.factory() as db:
            slots = db.scalars(select(MultipleChoiceQuestion).where(MultipleChoiceQuestion.session_id == state["id"])
                               .order_by(MultipleChoiceQuestion.position)).all()
        assert [slot.source_card_id for slot in slots] == [first.id, cached.id]
        assert slots[0].options is None
        cached_options = slots[1].options
        assert len(cached_options) == 4
        assert slots[1].front_image == slots[1].back_image == photo
        with mc.factory.begin() as db:
            card = db.get(Flashcard, cached.id)
            card.front_image = card.back_image = None
    finally:
        release.set()
    wait_for_state(mc, path, "active")
    question = mc.get(path + "/question").json()
    assert question["front"] == first.front
    assert mc.post(path + "/answer", json={
        "question_id": question["id"], "option_id": next(o["id"] for o in question["options"] if o["text"] == first.back),
    }).status_code == 200
    next_question = mc.get(path + "/question").json()
    assert next_question["front"] == cached.front and next_question["options"] == cached_options
    assert next_question["front_image"] == photo
    grade = mc.post(path + "/answer", json={
        "question_id": next_question["id"], "option_id": next(o["id"] for o in next_question["options"] if o["text"] == cached.back),
    })
    assert grade.status_code == 200 and grade.json()["back_image"] == photo


def test_warm_session_finishes_while_another_session_owns_the_model_slot(mc, monkeypatch):
    cold_deck, warm_deck = deck(mc), deck(mc)
    with mc.factory() as db:
        owner = db.get(User, mc.test_user_id)
        warm_card = db.scalar(select(Flashcard.id).where(Flashcard.deck_id == warm_deck))
    mock_generation(monkeypatch, return_value=CHOICES)
    asyncio.run(distractor_cache.get_or_generate_distractors(warm_card, owner))
    entered, release = Event(), Event()
    inference_calls = []

    async def generate(front, back, *, model):
        inference_calls.append(front)
        entered.set()
        while not release.is_set():
            await asyncio.sleep(0.01)
        return CHOICES

    monkeypatch.setattr(distractors, "generate_distractors", generate)
    cold_path, _ = start(mc, cold_deck)
    try:
        assert entered.wait(5)
        warm_path, _ = start(mc, warm_deck)
        assert wait_for_state(mc, warm_path, "active")["progress"]["ready"] == 1
        assert mc.get(cold_path).json()["status"] == "preparing"
        classic = mc.post(f"/api/decks/{warm_deck}/study")
        assert classic.status_code == 201
        review(mc, classic.json())
        assert len(inference_calls) == 1
    finally:
        release.set()
    wait_for_state(mc, cold_path, "active")


@pytest.mark.parametrize("stale", ["fingerprint", "model", "version", "choice", "provenance"])
def test_cache_pass_queues_invalid_entries_for_generation(mc, monkeypatch, stale):
    deck_id = deck(mc, count=2)
    generator = mock_generation(monkeypatch, return_value=CHOICES)
    with mc.factory() as db:
        owner = db.get(User, mc.test_user_id)
        target, source = db.scalars(select(Flashcard).where(Flashcard.deck_id == deck_id)
                                    .order_by(Flashcard.id)).all()
    asyncio.run(distractor_cache.get_or_generate_distractors(target.id, owner))
    asyncio.run(distractor_cache.get_or_generate_distractors(source.id, owner))
    generator.reset_mock()
    with mc.factory.begin() as db:
        row = db.get(FlashcardDistractorCache, target.id)
        if stale == "fingerprint":
            row.content_fingerprint = "0" * 64
        elif stale == "model":
            row.ollama_model = "old-model"
        elif stale == "version":
            row.generation_version -= 1
        elif stale == "choice":
            row.distractors = [target.back, *CHOICES[1:]]
        else:
            row.distractors = [source.back, *CHOICES[1:]]
            db.add(FlashcardDistractorSource(
                flashcard_id=target.id, position=0, source_card_id=source.id, content_fingerprint="0" * 64,
            ))
    path, _ = start(mc, deck_id)
    assert wait_for_state(mc, path, "active")["progress"]["ready"] == 2
    generator.assert_awaited_once_with(target.front, target.back, model=distractors.configured_model())
    with mc.factory() as db:
        assert db.get(FlashcardDistractorCache, target.id).distractors == CHOICES


@pytest.mark.parametrize("resolution", ["retry", "continue"])
@pytest.mark.parametrize("reason", ["insufficient_distractors", "invalid_ai_response"])
def test_partial_generation_failure_can_retry_or_continue(mc, monkeypatch, resolution, reason):
    deck_id = deck(mc, count=2)
    generate = mock_generation(monkeypatch, side_effect=[
        DistractorGenerationError("Private model report", reason=reason), CHOICES, CHOICES,
    ])
    path, _ = start(mc, deck_id)
    failed = wait_for_state(mc, path, "failed")
    assert failed["progress"] == {"total": 2, "completed": 2, "ready": 1, "failed": 1}
    assert len(failed["failures"]) == 1 and failed["failures"][0]["reason"] == reason
    assert "Private model report" not in json.dumps(failed)
    assert mc.get(path + "/question").status_code == 409
    response = mc.post(path + "/" + resolution)
    assert response.status_code == (202 if resolution == "retry" else 200)
    active = wait_for_state(mc, path, "active")
    assert active["progress"]["ready"] == (2 if resolution == "retry" else 1)
    assert generate.await_count == (3 if resolution == "retry" else 2)
    if resolution == "continue":
        question = mc.get(path + "/question").json()
        graded = mc.post(path + "/answer", json={
            "question_id": question["id"], "option_id": next(o["id"] for o in question["options"] if o["text"] not in CHOICES),
        }).json()
        assert graded["session"]["status"] == "completed"
        assert graded["session"]["failures"] == failed["failures"]


def test_preparation_deadline_marks_remaining_cards_failed(mc, monkeypatch):
    monkeypatch.setattr(study, "PREPARATION_TIMEOUT", 0.15)

    async def stall(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(distractors, "generate_distractors", stall)
    path, _ = start(mc, deck(mc))
    state = wait_for_state(mc, path, "failed")
    assert state["progress"] == {"total": 1, "completed": 1, "ready": 0, "failed": 1}
    assert state["failures"][0]["reason"] == "preparation_timeout"
    assert mc.post(path + "/continue").status_code == 409
    mock_generation(monkeypatch, return_value=CHOICES)
    monkeypatch.setattr(study, "PREPARATION_TIMEOUT", 900)
    assert mc.post(path + "/retry").status_code == 202
    wait_for_state(mc, path, "active")


def test_cancel_awaits_running_generation_and_prevents_partial_writes(mc, monkeypatch):
    started, stopped = Event(), Event()

    async def stall(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(distractors, "generate_distractors", stall)
    path, _ = start(mc, deck(mc, count=2))
    assert started.wait(5)
    assert mc.post(path + "/cancel").json()["status"] == "cancelled"
    assert stopped.is_set()
    assert mc.post(path + "/cancel").status_code == 200
    assert mc.post(path + "/retry").status_code == 409
    assert mc.get(path + "/question").status_code == 409
    assert mc.get(path).json()["progress"]["ready"] == 0
    with mc.factory() as db:
        assert db.scalar(select(FlashcardDistractorCache)) is None


@pytest.mark.parametrize("change,reason", [("edit", "card_changed"), ("delete", "card_missing")])
def test_source_changes_during_generation_are_reported(mc, monkeypatch, change, reason):
    started, release = Event(), Event()

    async def generate(*args, **kwargs):
        started.set()
        while not release.is_set():
            await asyncio.sleep(0.01)
        return CHOICES

    monkeypatch.setattr(distractors, "generate_distractors", generate)
    deck_id = deck(mc)
    path, _ = start(mc, deck_id)
    assert started.wait(5)
    with mc.factory() as db:
        card_id = db.scalar(select(Flashcard.id).where(Flashcard.deck_id == deck_id))
    try:
        if change == "edit":
            assert mc.patch(f"/api/cards/{card_id}", json={"front": "Edited question"}).status_code == 200
        else:
            assert mc.delete(f"/api/cards/{card_id}").status_code == 204
    finally:
        release.set()
    state = wait_for_state(mc, path, "failed")
    assert state["failures"] == [{"card_id": card_id, "reason": reason}]
    assert state["progress"]["ready"] == 0


def test_expired_session_cannot_be_answered_cancelled_or_retried(mc, monkeypatch):
    mock_generation(monkeypatch, return_value=CHOICES)
    path, state = start(mc, deck(mc))
    wait_for_state(mc, path, "active")
    question = mc.get(path + "/question").json()
    with mc.factory.begin() as db:
        db.get(MultipleChoiceSession, state["id"]).expires_at = utcnow() - timedelta(seconds=1)
    assert mc.get(path).json()["status"] == "expired"
    assert mc.get(path + "/question").status_code == 410
    assert mc.post(path + "/answer", json={
        "question_id": question["id"], "option_id": question["options"][0]["id"],
    }).status_code == 410
    assert mc.post(path + "/cancel").status_code == 410
    assert mc.post(path + "/retry").status_code == 410


def test_boot_recovery_marks_unfinished_preparations_retryable(mc, monkeypatch):
    deck_id = deck(mc)
    state, _ = study.create_session(deck_id, mc.test_user_id)
    path = f"/api/multiple-choice/{state['id']}"
    study.recover_interrupted()
    failed = mc.get(path).json()
    assert failed["status"] == "failed"
    assert failed["failures"][0]["reason"] == "interrupted"
    mock_generation(monkeypatch, return_value=CHOICES)
    assert mc.post(path + "/retry").status_code == 202
    wait_for_state(mc, path, "active")


@pytest.mark.parametrize("correct", [True, False])
def test_duplicate_concurrent_submission_does_not_consume_an_extra_try(mc, monkeypatch, correct):
    mock_generation(monkeypatch, return_value=CHOICES)
    path, _ = start(mc, deck(mc))
    wait_for_state(mc, path, "active")
    question = mc.get(path + "/question").json()
    option = next(option for option in question["options"] if (option["text"] not in CHOICES) == correct)
    body = {"question_id": question["id"], "option_id": option["id"]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        calls = [pool.submit(mc.post, path + "/answer", json=body) for _ in range(2)]
        assert sorted(call.result(timeout=6).status_code for call in calls) == [200, 409]
    assert mc.get(path).json()["answered"] == int(correct)


def test_first_presentation_allows_retry_and_repeat_session_only_one_try(mc, monkeypatch):
    mock_generation(monkeypatch, return_value=CHOICES)
    deck_id = deck(mc)
    first, _ = start(mc, deck_id)
    wait_for_state(mc, first, "active")
    question = mc.post(first + "/question").json()["question"]
    assert question["attempts_remaining"] == 2
    # A second session also sees the card, even before the first session answers it.
    repeat, _ = start(mc, deck_id)
    wait_for_state(mc, repeat, "active")
    for path, current in ((repeat, mc.post(repeat + "/question").json()["question"]), (first, question)):
        wrong = next(o["id"] for o in current["options"] if o["text"] in CHOICES)
        result = mc.post(path + "/answer", json={"question_id": current["id"], "option_id": wrong}).json()
        assert result["is_correct"] is False
        if path == repeat:
            assert current["attempts_remaining"] == 1
            assert result["session"]["status"] == "completed" and "correct_option" in result
        else:
            assert result["retry"] and "correct_option" not in result and "back_image" not in result
            reopened = mc.post(path + "/question").json()["question"]
            assert reopened == {**question, "eliminated_option_id": wrong, "attempts_remaining": 1}
            correct = next(o["id"] for o in reopened["options"] if o["text"] not in CHOICES)
            final = mc.post(path + "/answer", json={"question_id": reopened["id"], "option_id": correct}).json()
            assert final["session"]["correct"] == final["session"]["answered"] == 1


@pytest.mark.parametrize("scope", ["question", "deck"])
def test_timed_sessions_enforce_the_deadline_across_requests(mc, monkeypatch, scope):
    mock_generation(monkeypatch, return_value=CHOICES)
    deck_id = deck(mc, count=2)
    now = utcnow()
    monkeypatch.setattr(study, "utcnow", lambda: now)
    start_response = mc.post(f"/api/decks/{deck_id}/multiple-choice", json={"scope": scope, "seconds": 10})
    assert start_response.status_code == 202
    path = f"/api/multiple-choice/{start_response.json()['id']}"
    wait_for_state(mc, path, "active")
    now += timedelta(minutes=2)
    assert mc.get(path + "/question").status_code == 409
    opened = mc.post(path + "/question").json()
    question = opened["question"]
    assert opened["remaining_ms"] == 10000
    assert set(question) == {"id", "front", "front_image", "options", "eliminated_option_id", "attempts_remaining"}
    now += timedelta(seconds=4)
    wrong = next(o["id"] for o in question["options"] if o["text"] in CHOICES)
    assert mc.post(path + "/answer", json={"question_id": question["id"], "option_id": wrong}).json()["retry"]
    resumed = mc.post(path + "/question").json()
    assert resumed["question"] == {**question, "eliminated_option_id": wrong, "attempts_remaining": 1}
    assert resumed["remaining_ms"] == 6000

    now += timedelta(seconds=6)
    late = {"question_id": question["id"], "option_id": question["options"][0]["id"]}
    assert mc.post(path + "/answer", json=late).status_code == 409
    state = mc.post(path + "/question").json()
    assert state["session"]["answered"] == 0
    if scope == "deck":
        assert state["session"]["status"] == "completed"
        assert state["session"]["timed_out"] == 2
        assert state["question"] is None
        assert mc.get(path).json() == state["session"]
    else:
        assert state["session"]["status"] == "active"
        assert state["session"]["timed_out"] == 1
        assert state["remaining_ms"] == 10000
        assert state["question"]["id"] != question["id"]
        now += timedelta(seconds=10)
        final = mc.post(path + "/question").json()
        assert final["session"]["status"] == "completed"
        assert final["session"]["timed_out"] == 2
        assert final["question"] is None


def test_deck_limit_keeps_answers_submitted_before_timeout(mc, monkeypatch):
    mock_generation(monkeypatch, return_value=CHOICES)
    deck_id = deck(mc, count=2)
    now = utcnow()
    monkeypatch.setattr(study, "utcnow", lambda: now)
    response = mc.post(f"/api/decks/{deck_id}/multiple-choice", json={"scope": "deck", "seconds": 10})
    assert response.status_code == 202
    path = f"/api/multiple-choice/{response.json()['id']}"
    wait_for_state(mc, path, "active")
    question = mc.post(path + "/question").json()["question"]
    now += timedelta(seconds=4)
    graded = mc.post(path + "/answer", json={
        "question_id": question["id"], "option_id": next(o["id"] for o in question["options"] if o["text"] not in CHOICES),
    })
    assert graded.status_code == 200
    assert mc.post(path + "/question").json()["remaining_ms"] == 6000
    now += timedelta(seconds=6)
    completed = mc.get(path).json()
    assert (completed["status"], completed["answered"], completed["timed_out"]) == ("completed", 1, 1)
    assert completed["correct"] == int(graded.json()["is_correct"])


def test_timing_migration_preserves_existing_multiple_choice_sessions(mc, monkeypatch):
    mock_generation(monkeypatch, return_value=CHOICES)
    path, _ = start(mc, deck(mc))
    before = wait_for_state(mc, path, "active")
    question = mc.get(path + "/question").json()
    engine = mc.factory.kw["bind"]
    with engine.begin() as db:
        for field in ("timing_scope", "timing_seconds", "deck_deadline"):
            db.execute(text(f"ALTER TABLE multiple_choice_sessions DROP COLUMN {field}"))
        for field in ("question_deadline", "timed_out_at", "allows_retry", "eliminated_option_id"):
            db.execute(text(f"ALTER TABLE multiple_choice_questions DROP COLUMN {field}"))
    init_database(engine)
    init_database(engine)
    assert mc.get(path).json() == before
    assert mc.get(path + "/question").json() == question


def test_progressive_study_obeys_the_shuffled_prefix_and_waits_at_gaps(mc, monkeypatch):
    deck_id = deck(mc, count=9)
    with mc.factory.begin() as db:
        owner = db.get(User, mc.test_user_id)
        order = list(db.scalars(select(Flashcard).where(Flashcard.deck_id == deck_id)
                                .order_by(Flashcard.id.desc())))
        for card in order:
            card.back = "Repeated answer"
    monkeypatch.setattr(study, "random", SimpleNamespace(shuffle=lambda items: items.reverse()))
    mock_generation(monkeypatch, return_value=CHOICES)
    for index in (2, 4, 6, 7, 8):
        asyncio.run(distractor_cache.get_or_generate_distractors(order[index].id, owner))

    first, tail, release_first, release_tail = Event(), Event(), Event(), Event()

    async def generate(front, back, *, model):
        if front == order[0].front:
            first.set()
            while not release_first.is_set():
                await asyncio.sleep(0.01)
        if front == order[5].front:
            tail.set()
            while not release_tail.is_set():
                await asyncio.sleep(0.01)
            raise DistractorGenerationError("No valid choices")
        return CHOICES

    monkeypatch.setattr(distractors, "generate_distractors", generate)
    path, _ = start(mc, deck_id)
    try:
        assert first.wait(5)
        state = mc.get(path).json()
        assert state["progress"]["ready"] == 5 and not state["can_start"]
        assert state["opening"] == {"ready": 0, "target": 5}
        assert mc.post(path + "/start").status_code == 409
        release_first.set()
        assert tail.wait(5)
        state = mc.get(path).json()
        assert state["can_start"] and state["opening"] == {"ready": 5, "target": 5}
        with ThreadPoolExecutor(max_workers=2) as pool:
            starts = [pool.submit(mc.post, path + "/start") for _ in range(2)]
            assert all(call.result(timeout=5).status_code == 200 for call in starts)
        for expected in order[:5]:
            question = mc.get(path + "/question").json()
            assert question["front"] == expected.front
            assert mc.get(path + "/question").json() == question
            correct = next(option for option in question["options"] if option["text"] == expected.back)
            response = mc.post(path + "/answer", json={"question_id": question["id"], "option_id": correct["id"]})
            assert response.status_code == 200
            assert response.json()["is_correct"]
        state = mc.get(path).json()
        assert state["status"] == "active" and state["preparing"] and not state["question_ready"]
        assert mc.get(path + "/question").status_code == 409
    finally:
        release_first.set()
        release_tail.set()

    deadline = monotonic() + 5
    while mc.get(path).json()["preparing"] and monotonic() < deadline:
        sleep(0.02)
    state = mc.get(path).json()
    assert not state["preparing"]
    assert state["failures"] == [{"card_id": order[5].id, "reason": "insufficient_distractors"}]
    for expected in order[6:]:
        question = mc.get(path + "/question").json()
        assert question["front"] == expected.front
        correct = next(option for option in question["options"] if option["text"] == expected.back)
        assert mc.post(path + "/answer", json={
            "question_id": question["id"], "option_id": correct["id"],
        }).status_code == 200
    assert mc.get(path).json()["status"] == "completed"


def stage_progressive_prefix(mc, count=7, timing=None, failed_first=False):
    deck_id = deck(mc, count=count)
    state, _ = study.create_session(deck_id, mc.test_user_id, timing)
    with mc.factory.begin() as db:
        slots = db.scalars(select(MultipleChoiceQuestion).where(MultipleChoiceQuestion.session_id == state["id"])
                           .order_by(MultipleChoiceQuestion.position)).all()
        if failed_first:
            slots[0].failure = "insufficient_distractors"
        offset = int(failed_first)
        for slot in slots[offset:offset + 5]:
            study._snapshot(slot, db.get(Flashcard, slot.source_card_id), CHOICES)
    return f"/api/multiple-choice/{state['id']}", slots


def test_progressive_recovery_retries_only_interrupted_positions(mc, monkeypatch):
    path, slots = stage_progressive_prefix(mc, failed_first=True)
    assert mc.post(path + "/start").status_code == 200
    first = mc.get(path + "/question").json()
    assert first["id"] == slots[1].id
    study.recover_interrupted()
    recovered = mc.get(path).json()
    assert recovered["status"] == "failed" and recovered["study_started"]
    assert {item["reason"] for item in recovered["failures"]} == {"interrupted", "insufficient_distractors"}
    generator = mock_generation(monkeypatch, return_value=CHOICES)
    assert mc.post(path + "/retry").status_code == 202
    deadline = monotonic() + 5
    while mc.get(path).json()["preparing"] and monotonic() < deadline:
        sleep(0.02)
    state = mc.get(path).json()
    assert state["status"] == "active" and not state["preparing"]
    assert state["failures"] == [{"card_id": slots[0].source_card_id, "reason": "insufficient_distractors"}]
    assert mc.get(path + "/question").json() == first
    generator.assert_awaited_once()


@pytest.mark.parametrize("ending", ["cancel", "expired", "deck_timer"])
def test_progressive_terminal_states_stop_or_reject_inference(mc, monkeypatch, ending):
    now = utcnow()
    monkeypatch.setattr(study, "utcnow", lambda: now)
    timing = SimpleNamespace(scope="deck", seconds=10) if ending == "deck_timer" else None
    path, slots = stage_progressive_prefix(mc, timing=timing)
    assert mc.post(path + "/start").status_code == 200
    if timing:
        assert mc.post(path + "/question").json()["question"]["id"] == slots[0].id

    # Attach a real worker to the staged session and block its model request.
    began, stopped = Event(), Event()

    async def generate(*args, **kwargs):
        began.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(distractors, "generate_distractors", generate)
    if ending == "expired":
        now += timedelta(hours=24)
        assert mc.get(path).json()["status"] == "expired"
        assert mc.post(path + "/start").status_code == 410
        return

    # Restart recovery gives the HTTP retry endpoint an interrupted job to launch.
    study.recover_interrupted()
    assert mc.post(path + "/retry").status_code == 202
    assert began.wait(5)
    if ending == "cancel":
        assert mc.post(path + "/cancel").json()["status"] == "cancelled"
    else:
        now += timedelta(seconds=10)
        state = mc.get(path).json()
        assert state["status"] == "active" and state["preparing"] and state["deck_time_over"]
        opened = mc.post(path + "/question").json()
        assert opened["question"] is None
        assert opened["session"]["status"] == "completed" and not opened["session"]["preparing"]
        assert opened["session"]["timed_out"] == 5
    assert stopped.wait(5)


def test_short_deck_waits_until_every_slot_is_resolved(mc):
    path, slots = stage_progressive_prefix(mc, count=4)
    session_id = slots[0].session_id
    with mc.factory.begin() as db:
        last = db.get(MultipleChoiceQuestion, slots[-1].id)
        last.options = None
        last.correct_option_id = None
    assert not mc.get(path).json()["can_start"]
    assert mc.post(path + "/start").status_code == 409
    with mc.factory.begin() as db:
        study._settle(db, db.get(MultipleChoiceSession, session_id), "insufficient_distractors")
    state = mc.get(path).json()
    assert state["status"] == "failed" and state["progress"]["completed"] == 4
    assert mc.post(path + "/continue").status_code == 200
    assert mc.get(path + "/question").json()["id"] == slots[0].id


def test_progressive_migration_preserves_an_existing_ready_snapshot(mc, monkeypatch):
    mock_generation(monkeypatch, return_value=CHOICES)
    path, _ = start(mc, deck(mc))
    wait_for_state(mc, path, "active")
    snapshot = mc.get(path + "/question").json()
    engine = mc.factory.kw["bind"]
    with engine.begin() as db:
        for column in ("study_started_at", "preparation_finished_at"):
            db.execute(text(f"ALTER TABLE multiple_choice_sessions DROP COLUMN {column}"))
    init_database(engine)
    init_database(engine)
    state = mc.get(path).json()
    assert state["study_started"] and not state["preparing"]
    assert mc.get(path + "/question").json() == snapshot


def test_additive_upgrade_preserves_classic_history_and_deck_deletion_cascades(mc, monkeypatch):
    deck_id = deck(mc)
    classic = mc.post(f"/api/decks/{deck_id}/study").json()
    review(mc, classic)
    history_path = f"/api/decks/{deck_id}/sessions"
    # Exit so the duration in history remains stable while verifying migrations.
    assert mc.post(f"/api/study/{classic['id']}/exit").status_code == 200
    before = mc.get(history_path).json()
    engine = mc.factory.kw["bind"]
    with engine.begin() as db:
        db.execute(text("DROP TABLE multiple_choice_questions"))
        db.execute(text("DROP TABLE multiple_choice_sessions"))
    init_database(engine)
    init_database(engine)
    assert mc.get(history_path).json() == before
    assert len(mc.get(f"/api/decks/{deck_id}/cards").json()) == 1

    mock_generation(monkeypatch, return_value=CHOICES)
    path, _ = start(mc, deck_id)
    wait_for_state(mc, path, "active")
    assert mc.delete(f"/api/decks/{deck_id}").status_code == 204
    assert mc.get(path).status_code == 404
    with mc.factory() as db:
        assert db.scalar(select(MultipleChoiceSession)) is None
        assert db.scalar(select(MultipleChoiceQuestion)) is None
