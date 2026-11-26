"""Authoritative room rounds and ordered multiple-choice preparation."""

import asyncio
import logging
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select
from starlette.concurrency import run_in_threadpool

from app.database import write_transaction
from app.models import Flashcard, RoomMember, RoomQuestion, RoomSession, StudyRoom, User, utcnow
from app.services import achievements
from app.services.distractor_cache import (
    InsufficientDistractorsError, _fingerprint, get_or_generate_distractors,
)
from app.services.multiple_choice import START_QUESTIONS, preparation_timeout, shuffled_options
from app.services.presenters import iso
from app.services.study_rooms import (
    ACTIVE_PHASES, IDLE, authorized_deck, chat_view, close, connected, eligible, fail, lobby_view, members, round_players, touch,
)

COUNTDOWN = timedelta(seconds=5)
REVIEW = timedelta(seconds=5)
LEASE = timedelta(seconds=30)
logger = logging.getLogger(__name__)


def current_question(db, session):
    return db.get(RoomQuestion, (session.id, session.position))


def finish(room, session, now):
    room.phase = 'results'
    session.completed_at = now
    session.opened_at = session.deadline = None
    session.paused = False
    session.claim = session.claim_until = None
    touch(room)


def credit_host(db, room, session, now):
    """Credit the starting host once per room after a session played to its end.

    Only this path is a successful completion; other finish() calls are aborts. The host must
    still be a member, and at least one prepared, non-failed question must have been played.
    """
    host = session.host_id
    if host is None or db.get(RoomMember, (room.id, host)) is None:
        return
    played = db.scalar(select(RoomQuestion.position).where(
        RoomQuestion.session_id == session.id, RoomQuestion.failed.is_(False), RoomQuestion.options.is_not(None),
    ).limit(1))
    if played is not None:
        achievements.record(db, host, 'room_hosted', at=now, subject=room.id)


def advance(db, room, session, position, now):
    question = db.scalar(select(RoomQuestion).where(
        RoomQuestion.session_id == session.id, RoomQuestion.position >= position, RoomQuestion.failed.is_(False),
    ).order_by(RoomQuestion.position).limit(1))
    if question is None:
        finish(room, session, now)
        credit_host(db, room, session, now)
        return
    session.position = question.position
    if question.options is None:
        session.opened_at = session.deadline = None
        room.phase = 'waiting'
        touch(room)
        return
    session.opened_at = now
    session.deadline = now + timedelta(seconds=room.seconds) if session.mode == 'challenge' else None
    room.phase = 'question'
    touch(room)


def challenge_points(opened_at, submitted_at, seconds):
    elapsed = timedelta(0)
    if submitted_at:
        received = datetime.fromisoformat(submitted_at).replace(tzinfo=None)
        elapsed = max(timedelta(0), min(received - opened_at, timedelta(seconds=seconds)))
    microseconds = (elapsed.seconds + elapsed.days * 86400) * 1_000_000 + elapsed.microseconds
    # Integer half-up rounding avoids floating point differences between browsers.
    return max(100, (1_000_000_000 - 30 * microseconds + 500_000) // 1_000_000)


def standings(session):
    values = [
        {**player, 'correct':0, 'answered':0, 'questions':0, 'score':0, **session.scores.get(key, {})}
        for key, player in session.players.items()
    ]
    if session.mode == 'challenge':
        values.sort(key=lambda row: (-row['score'], -row['correct'], row['username']))
    return values


def reveal(room, session, question, now):
    stats = dict(session.scores)
    for player in session.players:
        guess = question.answers.get(player)
        correct = bool(guess and guess['option_id'] == question.correct_id)
        previous = stats.get(player, {})
        points = challenge_points(session.opened_at, guess['at'], room.seconds) if correct and session.mode == 'challenge' else 0
        stats[player] = {
            'score': previous.get('score', 0) + points,
            'correct': previous.get('correct', 0) + int(correct),
            'answered': previous.get('answered', 0) + int(bool(guess)),
            'questions': previous.get('questions', 0) + 1,
        }
    session.scores = stats
    room.phase = 'reveal'
    session.deadline = now + REVIEW
    touch(room)


def progress_round(db, room, session, now):
    if room.phase not in ACTIVE_PHASES:
        return
    if not authorized_deck(db, room):
        finish(room, session, now)
        return
    eligible_ids = {str(user.id) for member, user in round_players(db, room, session) if eligible(member, now)}
    if not eligible_ids:
        # Spectators cannot keep a round open after its active players are gone.
        finish(room, session, now)
        return
    if room.phase in {'preparing', 'waiting'}:
        return
    if room.phase == 'countdown':
        if session.deadline and now >= session.deadline:
            advance(db, room, session, 0, now)
        return
    if room.phase == 'reveal':
        if session.deadline and now >= session.deadline:
            advance(db, room, session, session.position + 1, now)
        return
    question = current_question(db, session)
    timed_out = session.deadline is not None and now >= session.deadline
    if timed_out or eligible_ids <= question.answers.keys():
        reveal(room, session, question, now)


def submit(db, room, member, user_id, session_id, position, option_id):
    session = db.get(RoomSession, room.session_id) if room.session_id else None
    now = utcnow()
    if not session or session.id != session_id or room.phase != 'question' or position != session.position:
        fail(409, 'That question is no longer accepting answers.')
    if not authorized_deck(db, room) or member.spectator or str(user_id) not in session.players:
        fail(403, 'You are spectating this session.')
    if session.deadline and now >= session.deadline:
        fail(409, 'Time is up for this question.')
    question = current_question(db, session)
    if option_id not in {option['id'] for option in question.options}:
        fail(422, 'Choose one of the displayed answers.')
    player = str(user_id)
    if player in question.answers:
        if question.answers[player]['option_id'] != option_id:
            fail(409, 'Your answer is already locked in.')
        return
    question.answers = {**question.answers, player: {'option_id': option_id, 'at': iso(now)}}
    member.seen_at = now
    member.disconnected_at = None
    touch(room)
    progress_round(db, room, session, now)


def study_view(db, room, viewer_id):
    view = lobby_view(db, room, viewer_id)
    view['chat'] = chat_view(db, room)
    session = db.get(RoomSession, room.session_id) if room.session_id else None
    if not session:
        return view
    view['session'] = {
        'id': session.id, 'position': session.position, 'total': session.total, 'failed': session.failed,
        'deadline': iso(session.deadline), 'paused': session.paused,
    }
    if session.mode == 'challenge':
        view['leaderboard'] = standings(session)
    if room.phase == 'results':
        view['results'] = standings(session)
    if room.phase not in {'question','reveal'} or not view['deck']:
        return view

    question = current_question(db, session)
    revealing = room.phase == 'reveal'
    mine = question.answers.get(str(viewer_id))
    answered = set(question.answers)
    for participant, (_, user) in zip(view['participants'], members(db, room)):
        participant['answered'] = str(user.id) in answered
    view['question'] = {
        'front': question.front, 'front_image': question.front_image, 'options': question.options,
        'selected_id': mine['option_id'] if mine else None,
    }
    if revealing:
        view['question'].update({
            'correct_id': question.correct_id, 'back_image': question.back_image,
            'responses': [{**player, 'option_id': question.answers.get(key, {}).get('option_id'),
                           'correct': question.answers.get(key, {}).get('option_id') == question.correct_id}
                          for key, player in session.players.items()],
        })
    return view


def unanswered_preparation():
    return select(RoomQuestion.position).where(
        RoomQuestion.session_id == RoomSession.id, RoomQuestion.options.is_(None),
        RoomQuestion.failed.is_(False),
    ).exists()


def next_unprepared(db, session):
    return db.scalar(select(RoomQuestion).where(
        RoomQuestion.session_id == session.id, RoomQuestion.options.is_(None), RoomQuestion.failed.is_(False),
    ).order_by(RoomQuestion.position).limit(1))


def claim_preparation(factory):
    now = utcnow()
    with factory() as db:
        pending = db.scalar(select(RoomSession.id).join(StudyRoom, StudyRoom.session_id == RoomSession.id)
                            .where(StudyRoom.phase.in_(ACTIVE_PHASES), unanswered_preparation(),
                                   or_(RoomSession.claim.is_(None), RoomSession.claim_until <= now)).limit(1))
    if not pending:
        return None
    with write_transaction(factory) as db:
        session = db.get(RoomSession, pending)
        room = db.get(StudyRoom, session.room_id) if session else None
        if not room or room.phase not in ACTIVE_PHASES or room.session_id != pending:
            return None
        if not next_unprepared(db, session) or (session.claim and session.claim_until > now):
            return None
        deck = authorized_deck(db, room)
        if not deck:
            finish(room, session, now)
            return None
        session.claim = str(uuid4())
        session.claim_until = now + LEASE
        return session.id, session.claim


def claimed(db, job):
    session = db.get(RoomSession, job[0])
    room = db.get(StudyRoom, session.room_id) if session else None
    if room and room.phase in ACTIVE_PHASES and room.session_id == job[0] and session.claim == job[1]:
        return room, session
    return None, None


def read_source(factory, job):
    with factory() as db:
        room, session = claimed(db, job)
        question = next_unprepared(db, session) if room else None
        if not question:
            return None
        deck = authorized_deck(db, room)
        card = db.get(Flashcard, question.card_id) if question.card_id else None
        if not deck or not card or card.deck_id != deck.id or _fingerprint(card.front, card.back) != question.fingerprint:
            return question.position, None
        return question.position, (card.id, deck.owner_id, (card.front, card.back))


def open_prepared_question(db, room, session, settled):
    if room.phase == 'waiting':
        advance(db, room, session, session.position, utcnow())
    elif room.phase == 'preparing':
        prepared = list(db.scalars(select(RoomQuestion.position).where(
            RoomQuestion.session_id == session.id, RoomQuestion.options.is_not(None),
        ).limit(START_QUESTIONS)))
        if settled or len(prepared) >= min(START_QUESTIONS, session.total):
            now = utcnow()
            if not prepared:
                finish(room, session, now)
                return
            room.phase = 'countdown'
            session.deadline = now + COUNTDOWN
            touch(room)


def save_question(factory, job, position, content, choices):
    with write_transaction(factory) as db:
        room, session = claimed(db, job)
        if not room:
            return False
        deck = authorized_deck(db, room)
        if not deck:
            finish(room, session, utcnow())
            return False
        question = next_unprepared(db, session)
        if not question or question.position != position:
            return False
        card = db.get(Flashcard, question.card_id) if question.card_id else None
        if choices and card and card.deck_id == deck.id and (card.front, card.back) == content:
            question.options, question.correct_id = shuffled_options(card.back, choices)
            question.front = card.front
            question.front_image, question.back_image = card.front_image, card.back_image
        else:
            question.failed = True
            session.failed += 1
        db.flush()
        open_prepared_question(db, room, session, settled=next_unprepared(db, session) is None)
        return True


def finalize(factory, job, aborted=False, timed_out=False):
    with write_transaction(factory) as db:
        room, session = claimed(db, job)
        if not room:
            return
        session.claim = session.claim_until = None
        if aborted:
            return
        if timed_out:
            for question in db.scalars(select(RoomQuestion).where(
                RoomQuestion.session_id == session.id, RoomQuestion.options.is_(None), RoomQuestion.failed.is_(False),
            )):
                question.failed = True
                session.failed += 1
            db.flush()
        if not authorized_deck(db, room):
            finish(room, session, utcnow())
        elif next_unprepared(db, session) is None:
            open_prepared_question(db, room, session, settled=True)


class RoomEngine:
    """Recover durable preparation and advance synchronized rounds without clients polling HTTP."""

    def __init__(self, factory, model_slot):
        self.factory = factory
        self.model_slot = model_slot
        self.connections = {}
        self.notification_subscribers = {}
        self.room_connections = {}
        self.job = None
        self.tasks = (asyncio.create_task(self._prepare()), asyncio.create_task(self._clock()))

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def _prepare(self):
        while True:
            job = None
            try:
                job = self.job = await run_in_threadpool(claim_preparation, self.factory)
                if job:
                    await self.prepare(job)
            except asyncio.CancelledError:
                if job:
                    await run_in_threadpool(finalize, self.factory, job, True)
                raise
            except Exception:
                logger.exception('Room preparation could not be completed')
                if job:
                    await run_in_threadpool(finalize, self.factory, job, False, True)
            finally:
                self.job = None
            await asyncio.sleep(.5)

    async def prepare(self, job):
        timed_out = False
        try:
            async with asyncio.timeout(preparation_timeout()):
                while entry := await run_in_threadpool(read_source, self.factory, job):
                    position, source = entry
                    choices, content = None, None
                    if source:
                        card_id, owner_id, content = source
                        try:
                            choices = await get_or_generate_distractors(
                                card_id, User(id=owner_id), expected_content=content, model_slot=self.model_slot)
                        except (InsufficientDistractorsError, HTTPException):
                            pass
                    if not await run_in_threadpool(save_question, self.factory, job, position, content, choices):
                        break
        except TimeoutError:
            timed_out = True
        await run_in_threadpool(finalize, self.factory, job, False, timed_out)

    async def _clock(self):
        while True:
            try:
                await run_in_threadpool(tick, self.factory, self.job)
            except Exception:
                logger.exception('Room state could not be advanced')
            await asyncio.sleep(1)


def tick(factory, job):
    now = utcnow()
    with factory() as db:
        room_ids = list(db.scalars(select(StudyRoom.id).where(StudyRoom.phase != 'closed')))
    if not room_ids:
        return
    with write_transaction(factory) as db:
        if job:
            _, session = claimed(db, job)
            if session:
                session.claim_until = now + LEASE
        for room in db.scalars(select(StudyRoom).where(StudyRoom.id.in_(room_ids), StudyRoom.phase != 'closed')):
            people = members(db, room)
            if not people or (room.updated_at < now - IDLE and
                              all(not member.seen_at or member.seen_at < now - IDLE for member, _ in people)):
                close(db, room)
                continue
            if not any(user.id == room.host_id and eligible(member, now) for member, user in people):
                replacement = next((user.id for member, user in people if connected(member, now)), None)
                if replacement is not None:
                    assign_host(db, room, replacement, now)
            session = db.get(RoomSession, room.session_id) if room.session_id else None
            if session and room.phase == 'preparing' and not authorized_deck(db, room):
                finish(room, session, now)
            if session:
                progress_round(db, room, session, now)


def assign_host(db, room, user_id, now):
    room.host_id = user_id
    for member, _ in members(db, room):
        member.ready = False
    session = db.get(RoomSession, room.session_id) if room.session_id else None
    if session and session.paused:
        session.paused = False
        session.deadline = now + REVIEW
    touch(room)
