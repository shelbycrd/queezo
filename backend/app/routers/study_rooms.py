import asyncio
from datetime import timedelta
from time import monotonic
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from starlette.concurrency import run_in_threadpool

from app.auth.config import get_settings
from app.auth.dependencies import require_user
from app.auth.service import hash_token, reserve_account_action
from app.database import get_db, get_db_factory, get_write_db, write_transaction
from app.models import AuthSession, Deck, Flashcard, RoomInvite, RoomMember, RoomSession, StudyRoom, User, utcnow
from app.services import room_study, study_rooms as rooms

router = APIRouter(prefix='/api/rooms', tags=['Study Rooms'])


class InviteInput(BaseModel):
    username: str = Field(min_length=3, max_length=32)


class SettingsInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    deck_id: int | None = Field(default=None, ge=1)
    mode: Literal['collaborative', 'challenge']
    seconds: int = Field(default=30, ge=10, le=120)
    share_private: bool = False
    expected_revision: str | None = Field(default=None, min_length=64, max_length=64)


class ReadyInput(BaseModel):
    ready: bool


class InvitationResponse(BaseModel):
    accept: bool


def overview_for(db, user_id):
    joined = db.scalars(select(StudyRoom).join(RoomMember).where(
        RoomMember.user_id == user_id, StudyRoom.phase != 'closed').order_by(StudyRoom.updated_at.desc()).limit(20))
    return {'invites': rooms.invitations(db, user_id),
            'rooms': [{'id': room.id, 'code': room.code, 'phase': room.phase} for room in joined]}


async def notify_invitation_changes(engine, user_ids):
    for user_id in set(user_ids):
        for changed in engine.notification_subscribers.get(user_id, ()):
            changed.set()


@router.get('')
def overview(user: User = Depends(require_user), db: Session = Depends(get_db)):
    consistent_read(db)
    return overview_for(db, user.id)


@router.post('', status_code=201)
def create(body: InviteInput, request: Request, tasks: BackgroundTasks, user: User = Depends(require_user), db: Session = Depends(get_write_db, scope='function')):
    if reserve_account_action(db, f'room-create:{user.id}', 12):
        rooms.fail(429, 'Too many room creations. Try again later.')
    room_id, recipient = rooms.create(db, user.id, body.username)
    tasks.add_task(notify_invitation_changes, request.app.state.room_engine, (user.id, recipient))
    return {'id': room_id, 'code': db.get(StudyRoom, room_id).code}


ROOM_LOOKUP_MISSES = 30


@router.get('/resolve/{reference}')
def resolve(reference: str, user: User = Depends(require_user), factory=Depends(get_db_factory)):
    """Map a public room code to the room for its members. Misses look identical and are throttled."""
    reference = reference[:36]
    with write_transaction(factory) as db:
        room = rooms.member_room(db, reference, user.id)
        if room:
            return {'id': room.id, 'code': room.code}
        # Commit the miss before failing so probing counts even though nothing is returned.
        blocked = reserve_account_action(db, f'room-lookup:{user.id}', ROOM_LOOKUP_MISSES)
    if blocked:
        rooms.fail(429, 'Too many room lookups. Try again later.')
    rooms.fail(404, 'Study room not found.')


@router.post('/{room_id}/invitation', status_code=204)
def respond(room_id: UUID, body: InvitationResponse, request: Request, tasks: BackgroundTasks, user: User = Depends(require_user),
            db: Session = Depends(get_write_db, scope='function')):
    rooms.respond(db, str(room_id), user.id, body.accept)
    tasks.add_task(notify_invitation_changes, request.app.state.room_engine, (user.id,))


def consistent_read(db):
    # sqlite3 does not begin a database transaction for SELECT in legacy mode.
    if not db.connection().connection.driver_connection.in_transaction:
        db.execute(text('BEGIN'))


@router.get('/{room_id}')
def room_state(room_id: UUID, user: User = Depends(require_user), db: Session = Depends(get_db)):
    consistent_read(db)
    room, _ = rooms.membership(db, str(room_id), user.id)
    return room_study.study_view(db, room, user.id)


@router.post('/{room_id}/invite', status_code=204)
def invite(room_id: UUID, body: InviteInput, request: Request, tasks: BackgroundTasks, user: User = Depends(require_user),
           db: Session = Depends(get_write_db, scope='function')):
    room, _ = rooms.membership(db, str(room_id), user.id)
    if reserve_account_action(db, f'room-invite:{user.id}', 30):
        rooms.fail(429, 'Too many room invitations. Try again later.')
    recipient = rooms.invite(db, room, user.id, body.username)
    tasks.add_task(notify_invitation_changes, request.app.state.room_engine, (recipient,))


@router.patch('/{room_id}/settings', status_code=204)
def settings(room_id: UUID, body: SettingsInput, user: User = Depends(require_user),
             db: Session = Depends(get_write_db, scope='function')):
    room, _ = rooms.membership(db, str(room_id), user.id)
    rooms.configure(db, room, user.id, body)


@router.post('/{room_id}/ready', status_code=204)
def ready(room_id: UUID, body: ReadyInput, user: User = Depends(require_user),
          db: Session = Depends(get_write_db, scope='function')):
    room, member = rooms.membership(db, str(room_id), user.id)
    if room.phase != 'lobby':
        rooms.fail(409, 'Ready is only available in the lobby.')
    if room.host_id == user.id:
        rooms.fail(403, 'The host does not mark themselves ready.')
    if member.spectator or not rooms.connected(member, utcnow()):
        rooms.fail(409, 'Join the lobby as a connected player before marking ready.')
    member.ready = body.ready
    rooms.touch(room)


@router.post('/{room_id}/start', status_code=204)
def start(room_id: UUID, user: User = Depends(require_user), db: Session = Depends(get_write_db, scope='function')):
    room, _ = rooms.membership(db, str(room_id), user.id)
    rooms.start(db, room, user.id)


@router.get('/{room_id}/friends')
def room_friends(room_id: UUID, page: int = Query(default=1, ge=1, le=10000),
                 user: User = Depends(require_user), db: Session = Depends(get_db)):
    consistent_read(db)
    room, _ = rooms.membership(db, str(room_id), user.id)
    return rooms.friends_page(db, room, user.id, page)


@router.get('/{room_id}/decks')
def room_decks(room_id: UUID, user: User = Depends(require_user), db: Session = Depends(get_db)):
    room, _ = rooms.membership(db, str(room_id), user.id)
    rooms.host_only(room, user.id)
    counts = select(func.count()).select_from(Flashcard).where(Flashcard.deck_id == Deck.id).scalar_subquery()
    return [dict(row) for row in db.execute(select(Deck.id, Deck.title, Deck.visibility, counts.label('card_count'))
            .where(Deck.unpublished_at.is_(None),
                   (Deck.owner_id == user.id) | ((Deck.visibility == 'public') & Deck.owner_id.is_not(None)))
            .order_by((Deck.owner_id == user.id).desc(), Deck.updated_at.desc()).limit(200)).mappings()]


class RoundInput(BaseModel):
    session_id: UUID
    position: int = Field(ge=0, le=149)


class AnswerInput(RoundInput):
    option_id: UUID


@router.post('/{room_id}/answer', status_code=204)
def answer(room_id: UUID, body: AnswerInput, user: User = Depends(require_user),
           db: Session = Depends(get_write_db, scope='function')):
    room, member = rooms.membership(db, str(room_id), user.id)
    room_study.submit(db, room, member, user.id, str(body.session_id), body.position, str(body.option_id))


def _live_session(db, token_hash, now):
    return db.scalar(select(AuthSession).join(User, User.id == AuthSession.user_id).where(
        AuthSession.token_hash == token_hash, AuthSession.expires_at > now, User.suspended_at.is_(None),
    ))


def _socket_room(db, room_id, token_hash, now):
    session = _live_session(db, token_hash, now)
    if not session:
        return None
    room = db.get(StudyRoom, room_id)
    member = db.get(RoomMember, (room_id, session.user_id))
    if not room or room.phase == 'closed' or not member:
        return None
    return room, member


def socket_state(factory, room_id, token_hash, *, refresh=False, reconnect=False):
    with factory() as db:
        consistent_read(db)
        now = utcnow()
        state = _socket_room(db, room_id, token_hash, now)
        if not state:
            return None
        room, member = state
        needs_heartbeat = reconnect or member.disconnected_at or not member.seen_at or now - member.seen_at >= timedelta(seconds=8)
        if not refresh or not needs_heartbeat:
            return member.user_id, room_study.study_view(db, room, member.user_id)

    with write_transaction(factory) as db:
        now = utcnow()
        state = _socket_room(db, room_id, token_hash, now)
        if not state:
            return None
        room, member = state
        if reconnect or member.disconnected_at or not member.seen_at or now - member.seen_at >= timedelta(seconds=8):
            member.disconnected_at = None
            member.seen_at = now
        return member.user_id, room_study.study_view(db, room, member.user_id)


def socket_session_hash(socket):
    settings = get_settings()
    token = socket.cookies.get(settings.cookie_name, '')
    if socket.headers.get('origin') in settings.trusted_origins and 40 <= len(token) <= 128:
        return hash_token(token)
    return None


def notification_state(factory, token_hash):
    with factory() as db:
        consistent_read(db)
        session = _live_session(db, token_hash, utcnow())
        if session:
            return session.user_id, overview_for(db, session.user_id)
    return None


@router.websocket('/notifications/live')
async def live_notifications(socket: WebSocket):
    token_hash = socket_session_hash(socket)
    if not token_hash:
        await socket.close(code=1008)
        return
    engine = socket.app.state.room_engine
    state = await run_in_threadpool(notification_state, engine.factory, token_hash)
    if not state:
        await socket.close(code=1008)
        return
    user_id, _ = state
    connections = engine.notification_subscribers
    if sum(map(len, connections.values())) >= 256 or len(connections.get(user_id, ())) >= 4:
        await socket.close(code=1013)
        return
    changed = asyncio.Event()
    subscribers = connections.setdefault(user_id, set())
    subscribers.add(changed)
    receiver = None
    try:
        await socket.accept()
        receiver = asyncio.create_task(socket.receive())
        previous = None
        sent_at = monotonic()
        while True:
            changed.clear()
            state = await run_in_threadpool(notification_state, engine.factory, token_hash)
            if not state:
                await socket.close(code=1008)
                return
            _, snapshot = state
            if snapshot != previous or monotonic() - sent_at >= 15:
                await socket.send_json(snapshot)
                previous, sent_at = snapshot, monotonic()
            waiter = asyncio.create_task(changed.wait())
            try:
                done, _ = await asyncio.wait({receiver, waiter}, timeout=5, return_when=asyncio.FIRST_COMPLETED)
                if receiver in done:
                    if receiver.result()['type'] != 'websocket.disconnect':
                        await socket.close(code=1008)
                    return
            finally:
                waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)
    except (WebSocketDisconnect, OSError):
        pass
    finally:
        if receiver:
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)
        subscribers.discard(changed)
        if not subscribers:
            connections.pop(user_id, None)


@router.websocket('/{room_id}/live')
async def live(socket: WebSocket, room_id: UUID):
    token_hash = socket_session_hash(socket)
    if not token_hash:
        await socket.close(code=1008)
        return
    room_id = str(room_id)
    engine = socket.app.state.room_engine
    factory = engine.factory
    initial = await run_in_threadpool(socket_state, factory, room_id, token_hash)
    if not initial:
        await socket.close(code=1008)
        return
    user_id, view = initial
    if sum(engine.connections.values()) >= 128 or engine.connections.get(user_id, 0) >= 4:
        await socket.close(code=1013)
        return
    engine.connections[user_id] = engine.connections.get(user_id, 0) + 1
    connection_key = (room_id, user_id)
    engine.room_connections[connection_key] = engine.room_connections.get(connection_key, 0) + 1
    try:
        initial = await run_in_threadpool(socket_state, factory, room_id, token_hash, refresh=True, reconnect=True)
        if not initial:
            await socket.close(code=1008)
            return
        _, view = initial
        await socket.accept()
        sent_at = heartbeat = monotonic()
        previous = None
        while True:
            server_time = view.pop('server_time')
            if view != previous or monotonic() - sent_at >= 15:
                await socket.send_json({**view, 'server_time': server_time})
                previous, sent_at = view, monotonic()
            try:
                # Answers and all other mutations use the CSRF-protected HTTP routes.
                event = await asyncio.wait_for(socket.receive(), timeout=.75)
                if event['type'] != 'websocket.disconnect':
                    await socket.close(code=1008)
                return
            except TimeoutError:
                pass
            refresh = monotonic() - heartbeat >= 10
            result = await run_in_threadpool(socket_state, factory, room_id, token_hash, refresh=refresh)
            if not result:
                await socket.close(code=1008)
                return
            _, view = result
            if refresh:
                heartbeat = monotonic()
    except (WebSocketDisconnect, OSError):
        pass
    finally:
        engine.connections[user_id] -= 1
        if not engine.connections[user_id]:
            del engine.connections[user_id]
        engine.room_connections[connection_key] -= 1
        if not engine.room_connections[connection_key]:
            del engine.room_connections[connection_key]
            await run_in_threadpool(mark_disconnected, factory, room_id, user_id, utcnow())


def mark_disconnected(factory, room_id, user_id, disconnected_at):
    with write_transaction(factory) as db:
        member = db.get(RoomMember, (room_id, user_id))
        if member and (not member.seen_at or member.seen_at <= disconnected_at):
            member.seen_at = member.disconnected_at = disconnected_at


class PauseInput(RoundInput):
    paused: bool


@router.post('/{room_id}/pause', status_code=204)
def pause(room_id: UUID, body: PauseInput, user: User = Depends(require_user),
          db: Session = Depends(get_write_db, scope='function')):
    room, _ = rooms.membership(db, str(room_id), user.id)
    rooms.host_only(room, user.id)
    session = db.get(RoomSession, room.session_id) if room.session_id else None
    if room.phase != 'reveal' or not session or session.mode != 'collaborative':
        rooms.fail(409, 'Pause is available during collaborative review.')
    now = utcnow()
    if session.id != str(body.session_id) or session.position != body.position or (session.deadline and session.deadline <= now):
        rooms.fail(409, 'That review is no longer active.')
    if session.paused != body.paused:
        session.paused = body.paused
        session.deadline = None if body.paused else now + room_study.REVIEW
        rooms.touch(room)


class ChatInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    text: str = Field(min_length=1, max_length=500)


class LeaveInput(BaseModel):
    action: Literal['leave', 'transfer', 'end']
    username: str | None = Field(default=None, min_length=3, max_length=32)


@router.post('/{room_id}/chat', status_code=204)
def chat(room_id: UUID, body: ChatInput, user: User = Depends(require_user),
         db: Session = Depends(get_write_db, scope='function')):
    room, _ = rooms.membership(db, str(room_id), user.id)
    if any((ord(char) < 32 and char not in '\n\t') or 0xD800 <= ord(char) <= 0xDFFF for char in body.text):
        rooms.fail(422, 'Remove unsupported characters from the message.')
    rooms.send_message(db, room, user, body.text)


@router.post('/{room_id}/leave', status_code=204)
def leave(room_id: UUID, body: LeaveInput, request: Request, tasks: BackgroundTasks, user: User = Depends(require_user),
          db: Session = Depends(get_write_db, scope='function')):
    room, member = rooms.membership(db, str(room_id), user.id)
    if room.host_id != user.id:
        if body.action != 'leave':
            rooms.fail(403, 'Only the host can transfer or end the room.')
    else:
        replacement = None
        if body.action != 'end':
            # Membership is returned in join order, independent of the leaderboard.
            replacement = next((candidate.id for _, candidate in rooms.members(db, room)
                                if candidate.id != user.id), None)
        if replacement is None:
            recipients = tuple(db.scalars(select(RoomInvite.user_id).where(RoomInvite.room_id == room.id)))
            tasks.add_task(notify_invitation_changes, request.app.state.room_engine, (user.id, *recipients))
            rooms.close(db, room)
            return
        room_study.assign_host(db, room, replacement, utcnow())
    rooms.leave(db, room, member)
    db.flush()
    session = db.get(RoomSession, room.session_id) if room.session_id else None
    if session and room.phase in room_study.ACTIVE_PHASES and not rooms.authorized_deck(db, room):
        room_study.finish(room, session, utcnow())


@router.post('/{room_id}/lobby', status_code=204)
def return_to_lobby(room_id: UUID, user: User = Depends(require_user),
                    db: Session = Depends(get_write_db, scope='function')):
    room, _ = rooms.membership(db, str(room_id), user.id)
    rooms.host_only(room, user.id)
    if room.phase != 'results':
        rooms.fail(409, 'The session is still in progress.')
    rooms.reset_lobby(db, room)
