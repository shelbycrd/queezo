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
    Flashcard, FlashcardDistractorCache, MultipleChoiceQuestion, MultipleChoiceSession, User, utcnow,
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
    assert set(question) == {"id", "front", "front_image", "options"}
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
            "question_id": question["id"], "option_id": question["options"][0]["id"],
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


def test_only_one_concurrent_submission_is_graded(mc, monkeypatch):
    mock_generation(monkeypatch, return_value=CHOICES)
    path, _ = start(mc, deck(mc))
    wait_for_state(mc, path, "active")
    question = mc.get(path + "/question").json()
    body = {"question_id": question["id"], "option_id": question["options"][0]["id"]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        calls = [pool.submit(mc.post, path + "/answer", json=body) for _ in range(2)]
        assert sorted(call.result(timeout=6).status_code for call in calls) == [200, 409]
    assert mc.get(path).json()["answered"] == 1


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
