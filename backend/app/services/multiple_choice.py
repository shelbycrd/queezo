"""Persistence and preparation for a single pass through a multiple-choice deck."""

import asyncio
import logging
import random
from collections import Counter
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

from anyio import CancelScope
from fastapi import HTTPException
from sqlalchemy import and_, func, select, text, update
from sqlalchemy.orm import load_only
from starlette.concurrency import run_in_threadpool

from app.database import SessionLocal
from app.models import Deck, Flashcard, MultipleChoiceQuestion, MultipleChoiceSession, User, utcnow
from app.services.activity import mark_study_day
from app.services.distractor_cache import (
    InsufficientDistractorsError, cached_choices_for_deck, get_or_generate_distractors,
)
from app.services.ownership import owned_flashcards
from app.services.inference_config import budget
from app.services.distractors import attempt_timeout
from app.services.presenters import iso
from app.services.limits import (
    history_media_available, history_media_remaining, media_bytes, media_size, require_operation_budget, require_study_slot,
)

PREPARATION_TIMEOUT = 900
START_QUESTIONS = 5
SESSION_LIFETIME = timedelta(hours=24)
MAX_ACCOUNT_PREPARATIONS = 3
MAX_PREPARATIONS = 16
MAX_PREPARATIONS_PER_WINDOW = 12
logger = logging.getLogger('uvicorn.error.queezo.preparation')


def preparation_timeout():
    return budget('MCQ_PREPARATION_TIMEOUT_SECONDS', PREPARATION_TIMEOUT, 1, 1800, parse=float)


def pending_limits():
    total = budget('MCQ_MAX_PENDING_JOBS', MAX_PREPARATIONS, 1, 64)
    personal = budget('MCQ_MAX_PENDING_PER_USER', MAX_ACCOUNT_PREPARATIONS, 1, 16)
    return total, min(total, personal)


def queue_busy():
    return HTTPException(429, 'Too many study sessions are preparing. Try again shortly.',
                         headers={'Retry-After': '5'})


@contextmanager
def _write():
    with SessionLocal.begin() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        yield db


def _owned_deck(db, deck_id, user_id):
    deck = db.scalar(select(Deck).where(Deck.id == deck_id, Deck.owner_id == user_id))
    if deck is None:
        raise HTTPException(404, "Deck not found.")
    return deck


def owned_session(db, session_id, user_id):
    session = db.scalar(select(MultipleChoiceSession).join(Deck).where(
        MultipleChoiceSession.id == session_id, MultipleChoiceSession.owner_id == user_id,
        Deck.owner_id == user_id,
    ))
    if session is None:
        raise HTTPException(404, "Multiple-choice session not found.")
    return session


def _questions(session_id):
    return select(MultipleChoiceQuestion).where(MultipleChoiceQuestion.session_id == session_id)


def _status(session, now=None):
    now = now or utcnow()
    if (session.status in {"active", "failed"} and session.preparation_finished_at is not None
            and _deck_time_over(session, now)):
        return "completed"
    if session.status in {"preparing", "failed", "active"} and session.expires_at <= now:
        return "expired"
    if session.status == "preparing" and session.prepare_until <= now:
        return "failed"
    return session.status


def _deck_time_over(session, now):
    return session.deck_deadline is not None and session.deck_deadline <= now


def _opening_progress(rows):
    target = min(START_QUESTIONS, len(rows))
    ready = 0
    for row in rows:
        if row.correct_option_id is not None:
            ready += 1
        elif not row.failure:
            break
        if ready == target:
            break
    return {"ready": ready, "target": target}


def _require_status(session, *allowed, now=None):
    status = _status(session, now)
    if status == "expired":
        raise HTTPException(410, "This multiple-choice session has expired.")
    if status not in allowed:
        raise HTTPException(409, "This action is unavailable in the current session state.")


def session_view(db, session):
    q = MultipleChoiceQuestion
    rows = db.execute(_questions(session.id).with_only_columns(
        q.source_card_id, q.correct_option_id, q.selected_option_id, q.failure, q.timed_out_at,
    ).order_by(q.position)).all()
    now = utcnow()
    status = _status(session, now)
    preparing = session.preparation_finished_at is None and status in {"preparing", "active"}
    next_slot = next((row for row in rows if row.selected_option_id is None
                      and row.timed_out_at is None and not row.failure), None)
    deck_time_over = _deck_time_over(session, now)
    opening = _opening_progress(rows)
    stalled = session.status == "preparing" and status in {"failed", "expired"}
    failures = [{"card_id": row.source_card_id, "reason": row.failure or "preparation_timeout"}
                for row in rows if row.failure or (stalled and row.correct_option_id is None)]
    ready = sum(row.correct_option_id is not None for row in rows)
    answered = sum(row.selected_option_id is not None for row in rows)
    correct = sum(row.selected_option_id is not None and row.selected_option_id == row.correct_option_id
                  for row in rows)
    finished_at = session.finished_at
    if status == "completed" and finished_at is None:
        finished_at = session.deck_deadline
    timing = {}
    if session.timing_scope is not None:
        deck_timed_out = status == "completed" and session.deck_deadline == finished_at and finished_at is not None
        timing = {
            "timing": {"scope": session.timing_scope, "seconds": session.timing_seconds},
            "timed_out": ready - answered if deck_timed_out else sum(row.timed_out_at is not None for row in rows),
            "deck_time_over": deck_time_over,
        }
    return {
        "id": session.id, "mode": "multiple_choice", "deck_id": session.deck_id,
        "deck_title": session.deck_title, "status": status,
        "preparing": preparing, "study_started": session.study_started_at is not None,
        "can_start": session.study_started_at is None and (status == "active" or (
            status == "preparing" and 0 < opening["target"] == opening["ready"]
        )),
        "question_ready": (status == "active" and not deck_time_over and next_slot is not None
                           and next_slot.correct_option_id is not None),
        "progress": {"total": len(rows), "completed": ready + len(failures),
                     "ready": ready, "failed": len(failures)},
        "opening": opening,
        "failures": failures, "answered": answered, "correct": correct,
        "created_at": iso(session.created_at), "expires_at": iso(session.expires_at),
        "finished_at": iso(finished_at), **timing,
    }


def require_preparation_slot(db, user_id):
    require_operation_budget(db, user_id, 'mc-prepare', MAX_PREPARATIONS_PER_WINDOW)
    now = utcnow()
    session = MultipleChoiceSession
    pending = select(func.count()).select_from(session).where(
        session.status.in_(('preparing', 'active')), session.preparation_finished_at.is_(None),
        session.prepare_until > now, session.expires_at > now,
    )
    total, personal = pending_limits()
    if db.scalar(pending.where(session.owner_id == user_id)) >= personal or db.scalar(pending) >= total:
        raise queue_busy()


def create_session(deck_id, user_id, timing=None):
    with _write() as db:
        deck = _owned_deck(db, deck_id, user_id)
        require_preparation_slot(db, user_id)
        require_study_slot(db, MultipleChoiceSession, user_id, deck.id)
        card_ids = list(db.scalars(owned_flashcards(user_id).with_only_columns(Flashcard.id)
                                  .where(Flashcard.deck_id == deck_id).order_by(Flashcard.id)))
        if not card_ids:
            raise HTTPException(409, "Add at least one flashcard before starting a study session.")
        random.shuffle(card_ids)
        now = utcnow()
        session = MultipleChoiceSession(
            id=str(uuid4()), deck_id=deck_id, deck_title=deck.title, owner_id=user_id,
            created_at=now, prepare_until=now + timedelta(seconds=preparation_timeout()),
            expires_at=now + SESSION_LIFETIME,
            timing_scope=timing.scope if timing else None,
            timing_seconds=timing.seconds if timing else None,
        )
        db.add(session)
        db.flush()
        db.add_all(MultipleChoiceQuestion(id=str(uuid4()), session_id=session.id,
                                        source_card_id=card_id, position=position)
                   for position, card_id in enumerate(card_ids))
        return session_view(db, session), session.attempt


def begin_study(session_id, user_id):
    with _write() as db:
        session = owned_session(db, session_id, user_id)
        _require_status(session, "preparing", "active")
        if session.study_started_at is None:
            if not session_view(db, session)["can_start"]:
                raise HTTPException(409, "The first questions are still preparing.")
            session.study_started_at = utcnow()
            session.status = "active"
        return session_view(db, session)


def retry_session(session_id, user_id):
    with _write() as db:
        session = owned_session(db, session_id, user_id)
        _require_status(session, "failed")
        require_preparation_slot(db, user_id)
        q = MultipleChoiceQuestion
        pending = update(q).where(q.session_id == session.id, q.options.is_(None))
        if session.study_started_at is not None:
            # Earlier permanent failures may already have been passed in the shuffled sequence.
            pending = pending.where(q.failure == "interrupted")
        db.execute(pending.values(failure=None))
        session.attempt += 1
        session.preparation_finished_at = None
        session.status = "active" if session.study_started_at is not None else "preparing"
        session.prepare_until = min(
            utcnow() + timedelta(seconds=preparation_timeout()), session.expires_at)
        return session_view(db, session), session.attempt


def _fail_pending(db, session_id, reason):
    db.execute(update(MultipleChoiceQuestion).where(
        MultipleChoiceQuestion.session_id == session_id,
        MultipleChoiceQuestion.options.is_(None), MultipleChoiceQuestion.failure.is_(None),
    ).values(failure=reason))


def continue_session(db, session):
    _require_status(session, "failed")
    _fail_pending(db, session.id, "preparation_timeout")
    if _next_question(db, session.id) is None and session.study_started_at is None:
        raise HTTPException(409, "No questions are ready. Retry preparation or use Classic Mode.")
    now = utcnow()
    session.preparation_finished_at = now
    session.study_started_at = session.study_started_at or now
    session.status = "active"
    _complete_if_done(db, session, now)
    return session_view(db, session)


def cancel_session(session_id, user_id):
    with _write() as db:
        session = owned_session(db, session_id, user_id)
        _require_status(session, "preparing", "failed", "active", "cancelled")
        if session.status != "cancelled":
            session.status = "cancelled"
            session.finished_at = utcnow()
            session.preparation_finished_at = session.preparation_finished_at or session.finished_at
        return session_view(db, session)


def history(db, deck_id, user_id, *, limit=50):
    _owned_deck(db, deck_id, user_id)
    sessions = list(db.scalars(select(MultipleChoiceSession).where(
        MultipleChoiceSession.deck_id == deck_id, MultipleChoiceSession.owner_id == user_id,
    ).order_by(MultipleChoiceSession.created_at.desc(), MultipleChoiceSession.id.desc()).limit(limit)))
    return [session_view(db, session) for session in sessions]


def _next_question(db, session_id):
    return db.scalar(_questions(session_id).where(
        MultipleChoiceQuestion.failure.is_(None), MultipleChoiceQuestion.answered_at.is_(None),
        MultipleChoiceQuestion.timed_out_at.is_(None),
    ).order_by(MultipleChoiceQuestion.position).limit(1))


def _complete_if_done(db, session, now):
    if session.preparation_finished_at is not None and _next_question(db, session.id) is None:
        session.status = "completed"
        session.finished_at = now


def _present(question):
    return {"id": question.id, "front": question.front, "front_image": question.front_image,
            "options": question.options, "eliminated_option_id": question.eliminated_option_id,
            "attempts_remaining": 2 if question.allows_retry and question.eliminated_option_id is None else 1}


def _record_presentation(db, session, question):
    if question.allows_retry is not None:
        return
    q = MultipleChoiceQuestion
    earlier = select(q.id).join(MultipleChoiceSession).where(
        q.source_card_id == question.source_card_id, q.id != question.id,
        MultipleChoiceSession.owner_id == session.owner_id,
        # Include known presentations from sessions created before retries were tracked.
        q.allows_retry.is_not(None) | q.answered_at.is_not(None) | q.question_deadline.is_not(None),
    )
    question.allows_retry = not db.scalar(select(earlier.exists()))


def _current_deadline(session, question):
    return session.deck_deadline if session.timing_scope == "deck" else question.question_deadline


def _require_open_question(session, question, now):
    if session.timing_scope is not None:
        deadline = _current_deadline(session, question)
        if deadline is None or deadline <= now:
            raise HTTPException(409, "Open the current timed question before answering.")


def question_view(db, session):
    now = utcnow()
    _require_status(session, "active", now=now)
    question = _next_question(db, session.id)
    if question is None or question.options is None or _deck_time_over(session, now):
        raise HTTPException(409, "The next question is not ready.")
    _require_open_question(session, question, now)
    return _present(question)


def open_owned_question(session_id, user_id, settle_stopped=False):
    with _write() as db:
        session = owned_session(db, session_id, user_id)
        if (settle_stopped and session.status == "active" and session.preparation_finished_at is None
                and _deck_time_over(session, utcnow())):
            _settle(db, session, "study_timeout")
        return open_question(db, session)


def open_question(db, session):
    """Record presentation and open or resume the timer under the write lock."""
    now = utcnow()
    status = _status(session, now)
    if status == "completed" and session.status in {"active", "failed"}:
        session.status = "completed"
        session.finished_at = session.deck_deadline
    if status != "active" or _deck_time_over(session, now):
        return {"session": session_view(db, session), "question": None, "remaining_ms": None}

    question = _next_question(db, session.id)
    if question is not None and question.question_deadline is not None and question.question_deadline <= now:
        question.timed_out_at = question.question_deadline
        question = _next_question(db, session.id)
    if question is None or question.options is None:
        _complete_if_done(db, session, now)
        deadline = session.deck_deadline if session.status == "active" else None
        return {"session": session_view(db, session), "question": None,
                "remaining_ms": max(1, (deadline - now) // timedelta(milliseconds=1)) if deadline else None}

    session.study_started_at = session.study_started_at or now
    _record_presentation(db, session, question)
    if session.timing_scope is not None and _current_deadline(session, question) is None:
        deadline = min(now + timedelta(seconds=session.timing_seconds), session.expires_at)
        if session.timing_scope == "deck":
            session.deck_deadline = deadline
        else:
            question.question_deadline = deadline
    deadline = _current_deadline(session, question)
    remaining_ms = max(1, (deadline - now) // timedelta(milliseconds=1)) if deadline is not None else None
    return {"session": session_view(db, session), "question": _present(question), "remaining_ms": remaining_ms}


def submit_answer(db, session, submission):
    now = utcnow()
    _require_status(session, "active", now=now)
    question = _next_question(db, session.id)
    if (question is None or question.options is None or question.id != submission.question_id
            or _deck_time_over(session, now)):
        raise HTTPException(409, "This question has changed or was already answered.")
    _require_open_question(session, question, now)
    if not any(option["id"] == submission.option_id for option in question.options):
        raise HTTPException(422, "Choose an option from the current question.")
    if submission.option_id == question.eliminated_option_id:
        raise HTTPException(409, "That option was already tried. Choose a different answer.")
    _record_presentation(db, session, question)
    session.study_started_at = session.study_started_at or now
    if (question.allows_retry and question.eliminated_option_id is None
            and submission.option_id != question.correct_option_id):
        question.eliminated_option_id = submission.option_id
        return {"question_id": question.id, "is_correct": False, "retry": True,
                "question": _present(question), "session": session_view(db, session)}
    question.selected_option_id = submission.option_id
    question.answered_at = now
    mark_study_day(db, session.owner_id)
    _complete_if_done(db, session, now)
    answer = next(option for option in question.options if option["id"] == question.correct_option_id)
    return {"question_id": question.id, "selected_option_id": question.selected_option_id,
            "is_correct": question.selected_option_id == question.correct_option_id,
            "correct_option": answer, "back_image": question.back_image,
            "session": session_view(db, session)}


def _settle(db, session, failure):
    now = utcnow()
    session.preparation_finished_at = now
    if _deck_time_over(session, now):
        _fail_pending(db, session.id, "study_timeout")
        session.status = "completed"
        session.finished_at = session.deck_deadline
        return
    _fail_pending(db, session.id, failure)
    if session.expires_at <= now:
        return
    q = MultipleChoiceQuestion
    blocked = q.failure.is_not(None) if session.study_started_at is None else q.failure == "interrupted"
    failed = db.scalar(_questions(session.id).with_only_columns(q.id).where(blocked).limit(1))
    session.status = "failed" if failed else "active"
    if session.status == "active":
        _complete_if_done(db, session, now)


def recover_interrupted():
    with _write() as db:
        for session in db.scalars(select(MultipleChoiceSession).where(
            MultipleChoiceSession.status.in_(("preparing", "active")),
            MultipleChoiceSession.preparation_finished_at.is_(None),
        )):
            _settle(db, session, "interrupted")


def _preparing(db, session_id, attempt):
    return db.scalar(select(MultipleChoiceSession).join(Deck).where(
        MultipleChoiceSession.id == session_id, MultipleChoiceSession.attempt == attempt,
        MultipleChoiceSession.status.in_(("preparing", "active")), MultipleChoiceSession.owner_id == Deck.owner_id,
        MultipleChoiceSession.preparation_finished_at.is_(None),
    ))


def _can_prepare(session):
    now = utcnow()
    return (session is not None and now < session.prepare_until
            and now < session.expires_at and not _deck_time_over(session, now))


def _prepare_cached(session_id, attempt):
    # Validate and snapshot cache hits atomically with card edits and cache invalidation.
    with _write() as db:
        session = _preparing(db, session_id, attempt)
        if not _can_prepare(session):
            return []
        q = MultipleChoiceQuestion
        pending = db.execute(
            _questions(session_id).add_columns(Flashcard)
            .outerjoin_from(q, Flashcard, and_(Flashcard.id == q.source_card_id, Flashcard.deck_id == session.deck_id))
            .options(load_only(Flashcard.id, Flashcard.front, Flashcard.back))
            .where(q.options.is_(None), q.failure.is_(None)).order_by(q.position)
        ).all()
        cards = {card.id: card for _, card in pending if card is not None}
        cached = cached_choices_for_deck(db, session.deck_id, cards)
        sizes = dict(db.execute(select(Flashcard.id, media_size(Flashcard))
                                .where(Flashcard.id.in_(cached))).all()) if cached else {}
        remaining = history_media_remaining(db, session.owner_id) if any(sizes.values()) else 0
        ready_ids = []
        misses = []
        for question, card in pending:
            if card is None:
                question.failure = "card_missing"
            elif card.id in cached:
                if sizes[card.id] <= remaining:
                    remaining -= sizes[card.id]
                    _snapshot(question, card, cached[card.id])
                    ready_ids.append(question.id)
                else:
                    question.failure = 'history_media_limit'
            else:
                misses.append((question.id, card.id))
        if ready_ids:
            # Copy photo blobs in SQLite instead of loading them all into the worker.
            db.execute(update(q).where(q.id.in_(ready_ids)).values(
                front_image=select(Flashcard.front_image).where(Flashcard.id == q.source_card_id).scalar_subquery(),
                back_image=select(Flashcard.back_image).where(Flashcard.id == q.source_card_id).scalar_subquery(),
            ).execution_options(synchronize_session=False))
    return misses


def _source_card(session, card_id):
    return owned_flashcards(session.owner_id).where(
        Flashcard.id == card_id, Flashcard.deck_id == session.deck_id,
    )


def _read_source(session_id, attempt, card_id):
    with SessionLocal() as db:
        session = _preparing(db, session_id, attempt)
        if not _can_prepare(session):
            return None
        content = db.execute(_source_card(session, card_id)
                             .with_only_columns(Flashcard.front, Flashcard.back)).one_or_none()
        return session.owner_id, tuple(content) if content is not None else None


def _save_prepared(session_id, attempt, question_id, content, choices, failure):
    with _write() as db:
        session = _preparing(db, session_id, attempt)
        if not _can_prepare(session):
            return
        question = db.get(MultipleChoiceQuestion, question_id)
        if question is None or question.session_id != session_id:
            return
        if failure:
            question.failure = failure
            return
        card = db.scalar(_source_card(session, question.source_card_id))
        if card is None:
            question.failure = "card_missing"
        elif (card.front, card.back) != content:
            question.failure = "card_changed"
        elif not history_media_available(db, session.owner_id, media_bytes(card.front_image, card.back_image)):
            question.failure = 'history_media_limit'
        else:
            _snapshot(question, card, choices)
            question.front_image = card.front_image
            question.back_image = card.back_image


def shuffled_options(back, choices):
    correct = {"id": str(uuid4()), "text": back}
    options = [correct, *({"id": str(uuid4()), "text": choice} for choice in choices)]
    random.shuffle(options)
    return options, correct["id"]


def _snapshot(question, card, choices):
    question.options, question.correct_option_id = shuffled_options(card.back, choices)
    question.front = card.front


def _finish(session_id, attempt, failure):
    with _write() as db:
        session = _preparing(db, session_id, attempt)
        if session is None:
            return
        _settle(db, session, failure or "preparation_timeout")


class PreparationJobs:
    """Own and cancel preparation tasks for the backend's single worker."""

    def __init__(self):
        # Validate deployment configuration before the application accepts work.
        pending_limits()
        preparation_timeout()
        attempt_timeout()
        self.model_slot = asyncio.Lock()
        self.tasks = {}
        self.current = {}
        self.reservations = Counter()
        self.closing = False

    async def submit(self, user_id, persist, *args):
        if self.closing:
            raise HTTPException(503, 'Study preparation is restarting. Try again shortly.',
                                headers={'Retry-After': '5'})
        total, personal = pending_limits()
        if (len(self.tasks) + self.reservations.total() >= total or
                list(self.tasks.values()).count(user_id) + self.reservations[user_id] >= personal):
            logger.info('Multiple-choice admission busy: pending=%s', len(self.tasks))
            raise queue_busy()
        self.reservations[user_id] += 1
        try:
            # Keep the durable reservation and in-process job registration together.
            with CancelScope(shield=True):
                state, attempt = await run_in_threadpool(persist, *args)
                self.start(state['id'], attempt, user_id)
            return state
        finally:
            self.reservations[user_id] -= 1
            if not self.reservations[user_id]:
                del self.reservations[user_id]

    def start(self, session_id, attempt, user_id=None):
        previous = self.current.get(session_id)
        if previous:
            previous_attempt, old = previous
            if previous_attempt >= attempt:
                return
            if not old.done() and not old.cancelling():
                old.cancel()
        task = asyncio.create_task(self._prepare(session_id, attempt))
        self.tasks[task] = user_id
        self.current[session_id] = (attempt, task)

        def forget(done):
            self.tasks.pop(done, None)
            if self.current.get(session_id) == (attempt, done):
                del self.current[session_id]
            if not done.cancelled() and done.exception() is not None:
                logger.error('Could not finalize multiple-choice preparation')

        task.add_done_callback(forget)

    async def cancel(self, session_id):
        entry = self.current.get(session_id)
        if entry is not None:
            _, task = entry
            if not task.done() and not task.cancelling():
                task.cancel()
            await asyncio.shield(asyncio.gather(task, return_exceptions=True))

    async def stop(self):
        self.closing = True
        tasks = tuple(self.tasks)
        for task in tasks:
            if not task.cancelling():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await run_in_threadpool(recover_interrupted)

    async def _prepare(self, session_id, attempt):
        failure = None
        failures = Counter()
        try:
            async with asyncio.timeout(preparation_timeout()):
                for question_id, card_id in await run_in_threadpool(_prepare_cached, session_id, attempt):
                    source = await run_in_threadpool(_read_source, session_id, attempt, card_id)
                    if source is None:
                        break
                    owner_id, content = source
                    reason, choices = None, None
                    if content is None:
                        reason = "card_missing"
                    else:
                        try:
                            choices = await get_or_generate_distractors(
                                card_id, User(id=owner_id), expected_content=content, model_slot=self.model_slot,
                            )
                        except InsufficientDistractorsError as error:
                            reason = error.reason
                        except HTTPException as error:
                            if error.status_code not in {404, 409}:
                                raise
                            reason = "card_missing" if error.status_code == 404 else "card_changed"
                    if reason:
                        failures[reason] += 1
                    await run_in_threadpool(
                        _save_prepared, session_id, attempt, question_id, content, choices, reason,
                    )
        except TimeoutError:
            failure = "preparation_timeout"
        except asyncio.CancelledError:
            failure = "interrupted"
            raise
        except Exception:
            logger.error('Multiple-choice preparation failed unexpectedly')
            failure = "preparation_failed"
        finally:
            if failure or failures:
                logger.info('Multiple-choice preparation settled: outcome=%s failed_cards=%s',
                            failure or 'partial_failure', sum(failures.values()))
            await run_in_threadpool(_finish, session_id, attempt, failure)
