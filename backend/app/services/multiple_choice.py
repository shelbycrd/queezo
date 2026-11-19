"""Persistence and preparation for a single pass through a multiple-choice deck."""

import asyncio
import logging
import random
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, text, update
from starlette.concurrency import run_in_threadpool

from app.database import SessionLocal
from app.models import Deck, Flashcard, MultipleChoiceQuestion, MultipleChoiceSession, User, utcnow
from app.services.activity import mark_study_day
from app.services.distractor_cache import InsufficientDistractorsError, get_or_generate_distractors
from app.services.ownership import owned_flashcards
from app.services.presenters import iso

PREPARATION_TIMEOUT = 900
SESSION_LIFETIME = timedelta(hours=24)
logger = logging.getLogger(__name__)


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


def _status(session):
    now = utcnow()
    if session.status in {"preparing", "failed", "active"} and session.expires_at <= now:
        return "expired"
    if session.status == "preparing" and session.prepare_until <= now:
        return "failed"
    return session.status


def _require_status(session, *allowed):
    status = _status(session)
    if status == "expired":
        raise HTTPException(410, "This multiple-choice session has expired.")
    if status not in allowed:
        raise HTTPException(409, "This action is unavailable in the current session state.")


def session_view(db, session):
    q = MultipleChoiceQuestion
    rows = db.execute(_questions(session.id).with_only_columns(
        q.source_card_id, q.correct_option_id, q.selected_option_id, q.failure,
    ).order_by(q.position)).all()
    status = _status(session)
    stalled = session.status == "preparing" and status in {"failed", "expired"}
    failures = [{"card_id": row.source_card_id, "reason": row.failure or "preparation_timeout"}
                for row in rows if row.failure or (stalled and row.correct_option_id is None)]
    ready = sum(row.correct_option_id is not None for row in rows)
    answered = sum(row.selected_option_id is not None for row in rows)
    correct = sum(row.selected_option_id is not None and row.selected_option_id == row.correct_option_id
                  for row in rows)
    return {
        "id": session.id, "mode": "multiple_choice", "deck_id": session.deck_id,
        "deck_title": session.deck_title, "status": status,
        "progress": {"total": len(rows), "completed": ready + len(failures),
                     "ready": ready, "failed": len(failures)},
        "failures": failures, "answered": answered, "correct": correct,
        "created_at": iso(session.created_at), "expires_at": iso(session.expires_at),
        "finished_at": iso(session.finished_at),
    }


def create_session(deck_id, user_id):
    with _write() as db:
        deck = _owned_deck(db, deck_id, user_id)
        card_ids = list(db.scalars(owned_flashcards(user_id).with_only_columns(Flashcard.id)
                                  .where(Flashcard.deck_id == deck_id).order_by(Flashcard.id)))
        if not card_ids:
            raise HTTPException(409, "Add at least one flashcard before starting a study session.")
        random.shuffle(card_ids)
        now = utcnow()
        session = MultipleChoiceSession(
            id=str(uuid4()), deck_id=deck_id, deck_title=deck.title, owner_id=user_id,
            created_at=now, prepare_until=now + timedelta(seconds=PREPARATION_TIMEOUT),
            expires_at=now + SESSION_LIFETIME,
        )
        db.add(session)
        db.flush()
        db.add_all(MultipleChoiceQuestion(id=str(uuid4()), session_id=session.id,
                                        source_card_id=card_id, position=position)
                   for position, card_id in enumerate(card_ids))
        return session_view(db, session), session.attempt


def retry_session(session_id, user_id):
    with _write() as db:
        session = owned_session(db, session_id, user_id)
        _require_status(session, "failed")
        db.execute(update(MultipleChoiceQuestion).where(
            MultipleChoiceQuestion.session_id == session.id,
            MultipleChoiceQuestion.options.is_(None),
        ).values(failure=None))
        session.attempt += 1
        session.status = "preparing"
        session.prepare_until = min(
            utcnow() + timedelta(seconds=PREPARATION_TIMEOUT), session.expires_at)
        return session_view(db, session), session.attempt


def _fail_pending(db, session_id, reason):
    db.execute(update(MultipleChoiceQuestion).where(
        MultipleChoiceQuestion.session_id == session_id,
        MultipleChoiceQuestion.options.is_(None), MultipleChoiceQuestion.failure.is_(None),
    ).values(failure=reason))


def continue_session(db, session):
    _require_status(session, "failed")
    if _next_question(db, session.id) is None:
        raise HTTPException(409, "No questions are ready. Retry preparation or use Classic Mode.")
    _fail_pending(db, session.id, "preparation_timeout")
    session.status = "active"
    return session_view(db, session)


def cancel_session(session_id, user_id):
    with _write() as db:
        session = owned_session(db, session_id, user_id)
        _require_status(session, "preparing", "failed", "active", "cancelled")
        if session.status != "cancelled":
            session.status = "cancelled"
            session.finished_at = utcnow()
        return session_view(db, session)


def history(db, deck_id, user_id):
    _owned_deck(db, deck_id, user_id)
    sessions = list(db.scalars(select(MultipleChoiceSession).where(
        MultipleChoiceSession.deck_id == deck_id, MultipleChoiceSession.owner_id == user_id,
    ).order_by(MultipleChoiceSession.created_at.desc()).limit(50)))
    return [session_view(db, session) for session in sessions]


def _next_question(db, session_id):
    return db.scalar(_questions(session_id).where(
        MultipleChoiceQuestion.options.is_not(None), MultipleChoiceQuestion.answered_at.is_(None),
    ).order_by(MultipleChoiceQuestion.position).limit(1))


def question_view(db, session):
    _require_status(session, "active")
    question = _next_question(db, session.id)
    if question is None:
        raise HTTPException(409, "There are no unanswered questions.")
    return {"id": question.id, "front": question.front, "front_image": question.front_image,
            "options": question.options}


def submit_answer(db, session, submission):
    _require_status(session, "active")
    question = _next_question(db, session.id)
    if question is None or question.id != submission.question_id:
        raise HTTPException(409, "This question has changed or was already answered.")
    if not any(option["id"] == submission.option_id for option in question.options):
        raise HTTPException(422, "Choose an option from the current question.")
    question.selected_option_id = submission.option_id
    question.answered_at = utcnow()
    mark_study_day(db, session.owner_id)
    if _next_question(db, session.id) is None:
        session.status = "completed"
        session.finished_at = question.answered_at
    answer = next(option for option in question.options if option["id"] == question.correct_option_id)
    return {"question_id": question.id, "selected_option_id": question.selected_option_id,
            "is_correct": question.selected_option_id == question.correct_option_id,
            "correct_option": answer, "back_image": question.back_image,
            "session": session_view(db, session)}


def _settle(db, session, failure):
    _fail_pending(db, session.id, failure)
    has_failures = db.scalar(_questions(session.id).with_only_columns(MultipleChoiceQuestion.id)
                             .where(MultipleChoiceQuestion.failure.is_not(None)).limit(1))
    session.status = "failed" if has_failures else "active"


def recover_interrupted():
    with _write() as db:
        for session in db.scalars(select(MultipleChoiceSession).where(
            MultipleChoiceSession.status == "preparing",
        )):
            _settle(db, session, "interrupted")


def _preparing(db, session_id, attempt):
    return db.scalar(select(MultipleChoiceSession).join(Deck).where(
        MultipleChoiceSession.id == session_id, MultipleChoiceSession.attempt == attempt,
        MultipleChoiceSession.status == "preparing", MultipleChoiceSession.owner_id == Deck.owner_id,
    ))


def _pending(session_id):
    with SessionLocal() as db:
        q = MultipleChoiceQuestion
        return db.execute(_questions(session_id).with_only_columns(q.id, q.source_card_id)
                          .where(q.options.is_(None), q.failure.is_(None)).order_by(q.position)).all()


def _source_card(session, card_id):
    return owned_flashcards(session.owner_id).where(
        Flashcard.id == card_id, Flashcard.deck_id == session.deck_id,
    )


def _read_source(session_id, attempt, card_id):
    with SessionLocal() as db:
        session = _preparing(db, session_id, attempt)
        if session is None or _status(session) != "preparing":
            return None
        content = db.execute(_source_card(session, card_id)
                             .with_only_columns(Flashcard.front, Flashcard.back)).one_or_none()
        return session.owner_id, tuple(content) if content is not None else None


def _save_prepared(session_id, attempt, question_id, content, choices, failure):
    with _write() as db:
        session = _preparing(db, session_id, attempt)
        if session is None or _status(session) != "preparing":
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
        else:
            correct = {"id": str(uuid4()), "text": card.back}
            options = [correct, *({"id": str(uuid4()), "text": choice} for choice in choices)]
            random.shuffle(options)
            question.options = options
            question.correct_option_id = correct["id"]
            question.front = card.front
            question.front_image = card.front_image
            question.back_image = card.back_image


def _finish(session_id, attempt, failure):
    with _write() as db:
        session = _preparing(db, session_id, attempt)
        if session is None:
            return
        _settle(db, session, failure or "preparation_timeout")


class PreparationJobs:
    """Own and cancel preparation tasks for the backend's single worker."""

    def __init__(self):
        self.model_slot = asyncio.Lock()
        self.tasks = set()
        self.current = {}

    def start(self, session_id, attempt):
        old = self.current.get(session_id)
        if old is not None:
            old.cancel()
        task = asyncio.create_task(self._prepare(session_id, attempt))
        self.tasks.add(task)
        self.current[session_id] = task

        def forget(done):
            self.tasks.discard(done)
            if self.current.get(session_id) is done:
                del self.current[session_id]
            if not done.cancelled() and done.exception() is not None:
                logger.error("Could not finalize multiple-choice preparation for %s", session_id)

        task.add_done_callback(forget)

    async def cancel(self, session_id):
        task = self.current.get(session_id)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def stop(self):
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await run_in_threadpool(recover_interrupted)

    async def _prepare(self, session_id, attempt):
        failure = None
        try:
            async with asyncio.timeout(PREPARATION_TIMEOUT):
                for question_id, card_id in await run_in_threadpool(_pending, session_id):
                    async with self.model_slot:
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
                                    card_id, User(id=owner_id), expected_content=content,
                                )
                            except InsufficientDistractorsError as error:
                                reason = error.reason
                            except HTTPException as error:
                                if error.status_code not in {404, 409}:
                                    raise
                                reason = "card_missing" if error.status_code == 404 else "card_changed"
                    await run_in_threadpool(
                        _save_prepared, session_id, attempt, question_id, content, choices, reason,
                    )
        except TimeoutError:
            failure = "preparation_timeout"
        except asyncio.CancelledError:
            failure = "interrupted"
            raise
        except Exception:
            logger.error("Multiple-choice preparation failed unexpectedly for %s", session_id)
            failure = "preparation_failed"
        finally:
            await run_in_threadpool(_finish, session_id, attempt, failure)
