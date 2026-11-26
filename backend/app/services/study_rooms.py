"""Membership and lobby operations for private multiplayer study rooms."""

import random
import re
import secrets
from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import and_, case, delete, func, or_, select

from app.models import Deck, Flashcard, Friendship, LoginThrottle, RoomInvite, RoomMember, RoomMessage, RoomQuestion, RoomSession, StudyRoom, User, utcnow
from app.services.distractor_cache import _fingerprint
from app.services.presenters import iso

CAPACITY = 6
MAX_OPEN_ROOMS = 3
MAX_ROOMS = 100
MAX_PREPARING = 8
ACTIVE_PHASES = ('preparing', 'countdown', 'waiting', 'question', 'reveal')
GRACE = timedelta(seconds=45)
IDLE = timedelta(minutes=30)
HEARTBEAT = timedelta(seconds=20)
FRIENDS_PER_PAGE = 4
# Per sender-recipient pair, rolling window. Never echo these values to clients.
INVITE_PAIR_LIMIT = 5
INVITE_PAIR_WINDOW = timedelta(seconds=60)
INVITE_PAIR_MESSAGE = "You've sent too many invitations to this user. Please try again later."


ROOM_CODE = re.compile(r'[0-9A-Fa-f]{8}')
ROOM_UUID = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')


def fail(status, message):
    raise HTTPException(status, message)


def identity(user):
    return {'username': user.username, 'display_name': user.display_name, 'avatar': user.avatar}


def membership(db, room_id, user_id):
    room = db.get(StudyRoom, room_id)
    member = db.get(RoomMember, (room_id, user_id)) if room else None
    if not room or not member:
        fail(404, 'Study room not found.')
    if room.phase == 'closed':
        fail(404, 'This study room has closed.')
    return room, member


def host_only(room, user_id):
    if room.host_id != user_id:
        fail(403, 'Only the host can do this.')


def members(db, room):
    return list(db.execute(select(RoomMember, User).join(User, User.id == RoomMember.user_id)
                           .where(RoomMember.room_id == room.id).order_by(RoomMember.joined_at, User.id)))


def touch(room):
    room.updated_at = utcnow()


def close(db, room):
    room.phase = 'closed'
    db.execute(delete(RoomInvite).where(RoomInvite.room_id == room.id))
    touch(room)


def eligible_friend(db, user_id, username):
    other = db.scalar(select(User).where(User.username == username.strip().lower()))
    friendship = db.get(Friendship, tuple(sorted((user_id, other.id)))) if other and other.id != user_id else None
    if not friendship or not friendship.accepted:
        fail(404, 'Choose someone from your friends list.')
    return other


def reserve_invite_attempt(db, sender_id, recipient_id):
    """Record one invitation attempt, or reject once the rolling pair window is full.

    Callers hold the BEGIN IMMEDIATE write transaction, so concurrent attempts
    serialize here and cannot all observe a free slot. Each of the fixed slots
    stores one attempt time; the generic throttle cleanup prunes stale rows.
    """
    now = utcnow()
    keys = [f'room-invite-pair:{sender_id}:{recipient_id}:{slot}' for slot in range(INVITE_PAIR_LIMIT)]
    slots = {row.key: row for row in db.scalars(select(LoginThrottle).where(LoginThrottle.key.in_(keys)))}
    free = next((key for key in keys if key not in slots), None)
    if free is not None:
        db.add(LoginThrottle(key=free, window_started=now, attempts=1))
        return
    oldest = min(slots.values(), key=lambda row: row.window_started)
    if oldest.window_started > now - INVITE_PAIR_WINDOW:
        fail(429, INVITE_PAIR_MESSAGE)
    oldest.window_started = now


def invite_friend(db, room, sender_id, other):
    if len(members(db, room)) >= CAPACITY:
        fail(409, 'This room is full.')
    if db.get(RoomMember, (room.id, other.id)):
        fail(409, 'That friend is already in the room.')
    # One active invitation per sender-recipient pair: a newer room supersedes older ones.
    stale = db.scalars(select(StudyRoom).join(RoomInvite, RoomInvite.room_id == StudyRoom.id).where(
        RoomInvite.sender_id == sender_id, RoomInvite.user_id == other.id, RoomInvite.room_id != room.id))
    for previous in stale:
        db.execute(delete(RoomInvite).where(RoomInvite.room_id == previous.id, RoomInvite.user_id == other.id))
        touch(previous)
    if not db.get(RoomInvite, (room.id, other.id)):
        db.add(RoomInvite(room_id=room.id, user_id=other.id, sender_id=sender_id))
        touch(room)


def invite(db, room, sender_id, username):
    other = eligible_friend(db, sender_id, username)
    reserve_invite_attempt(db, sender_id, other.id)
    invite_friend(db, room, sender_id, other)
    return other.id


def pending_lobby(db, sender_id, recipient_id):
    return db.scalar(select(StudyRoom.id).join(RoomInvite, RoomInvite.room_id == StudyRoom.id).where(
        StudyRoom.host_id == sender_id, StudyRoom.phase == 'lobby',
        RoomInvite.sender_id == sender_id, RoomInvite.user_id == recipient_id).limit(1))


def create(db, user_id, username):
    other = eligible_friend(db, user_id, username)
    reserve_invite_attempt(db, user_id, other.id)
    # Repeating "Invite to Study" reuses the pending lobby instead of opening duplicates.
    existing = pending_lobby(db, user_id, other.id)
    if existing:
        return existing, other.id
    if db.scalar(select(func.count()).select_from(StudyRoom)
                 .where(StudyRoom.host_id == user_id, StudyRoom.phase != 'closed')) >= MAX_OPEN_ROOMS:
        fail(429, 'Close an existing room before creating another.')
    if db.scalar(select(func.count()).select_from(StudyRoom).where(StudyRoom.phase != 'closed')) >= MAX_ROOMS:
        fail(429, 'Study rooms are busy. Try again later.')
    room = StudyRoom(id=str(uuid4()), code=new_code(db), host_id=user_id)
    db.add(room)
    db.flush()
    db.add(RoomMember(room_id=room.id, user_id=user_id, seen_at=utcnow()))
    db.flush()
    invite_friend(db, room, user_id, other)
    return room.id, other.id


def new_code(db):
    # Writers are serialized, so a code checked here cannot be claimed concurrently.
    while True:
        code = secrets.token_hex(4).upper()
        if not db.scalar(select(StudyRoom.id).where(StudyRoom.code == code)):
            return code


def member_room(db, reference, user_id):
    """Resolve a public code (or a legacy UUID link) to a room only for its current members."""
    if ROOM_CODE.fullmatch(reference):
        room = db.scalar(select(StudyRoom).where(StudyRoom.code == reference.upper()))
    elif ROOM_UUID.fullmatch(reference):
        room = db.get(StudyRoom, reference.lower())
    else:
        return None
    if not room or room.phase == 'closed' or not db.get(RoomMember, (room.id, user_id)):
        return None
    return room


def invitations(db, user_id):
    rows = db.execute(select(RoomInvite, User, StudyRoom.code).join(User, User.id == RoomInvite.sender_id)
                      .join(StudyRoom, StudyRoom.id == RoomInvite.room_id)
                      .where(RoomInvite.user_id == user_id, StudyRoom.phase != 'closed')
                      .order_by(RoomInvite.created_at.desc()))
    return [{'room_id': row.room_id, 'code': code, 'sender': identity(sender), 'sent_at': iso(row.created_at)}
            for row, sender, code in rows]


def respond(db, room_id, user_id, accept):
    request = db.get(RoomInvite, (room_id, user_id))
    room = db.get(StudyRoom, room_id)
    if accept and room and room.phase != 'closed' and db.get(RoomMember, (room_id, user_id)):
        return
    if not request or not room or room.phase == 'closed':
        fail(404, 'Invitation is no longer available.')
    if accept:
        sender = db.get(RoomMember, (room_id, request.sender_id))
        pair = db.get(Friendship, tuple(sorted((request.sender_id, user_id))))
        if not sender or not pair or not pair.accepted:
            fail(403, 'This invitation is no longer authorized.')
        if len(members(db, room)) >= CAPACITY:
            fail(409, 'This room is full.')
        db.add(RoomMember(room_id=room_id, user_id=user_id, spectator=room.phase != 'lobby', seen_at=utcnow()))
        touch(room)
    db.delete(request)


def authorized_deck(db, room):
    deck = db.get(Deck, room.deck_id) if room.deck_id is not None else None
    if not deck or deck.unpublished_at is not None or deck.owner_id != room.deck_owner_id:
        return None
    if deck.visibility == 'public':
        return deck
    if room.share_private and db.get(RoomMember, (room.id, deck.owner_id)):
        return deck
    return None


def settings_revision(room):
    values = (room.host_id, room.deck_id, room.mode, room.seconds, room.share_private)
    return sha256(repr(values).encode()).hexdigest()


def configure(db, room, user_id, settings):
    host_only(room, user_id)
    if room.phase != 'lobby':
        fail(409, 'Return to the lobby before changing settings.')
    if settings.expected_revision and settings.expected_revision != settings_revision(room):
        fail(409, 'Room settings changed. Check the latest settings and try again.')
    deck = db.get(Deck, settings.deck_id) if settings.deck_id is not None else None
    if settings.deck_id is not None and (not deck or deck.unpublished_at is not None or deck.owner_id is None or
            (deck.owner_id != user_id and deck.visibility != 'public')):
        fail(404, 'Deck not available.')
    # Selecting an owned private or unlisted deck grants access only in this room.
    share_private = bool(deck and deck.owner_id == user_id and deck.visibility != 'public')
    next_settings = (settings.deck_id, settings.mode, settings.seconds, share_private)
    if (room.deck_id, room.mode, room.seconds, room.share_private) != next_settings:
        for member, _ in members(db, room):
            if member.user_id != room.host_id:
                member.ready = False
    room.deck_id, room.mode, room.seconds, room.share_private = next_settings
    room.deck_owner_id = deck.owner_id if deck else None
    touch(room)


def eligible(member, now):
    return member.seen_at is not None and member.seen_at >= now - GRACE


def connected(member, now):
    return member.disconnected_at is None and member.seen_at is not None and member.seen_at >= now - HEARTBEAT


def round_players(db, room, session):
    return [(member, user) for member, user in members(db, room)
            if not member.spectator and str(user.id) in session.players]


def active_lineup(people, now):
    return [(member, user) for member, user in people if not member.spectator and connected(member, now)]


def readiness(room, lineup):
    if len(lineup) < 2 or not any(user.id == room.host_id for _, user in lineup):
        return 'At least two connected participants, including the host, are required.'
    if any(not member.ready for member, user in lineup if user.id != room.host_id):
        return 'Waiting for all connected participants except the host to be ready.'
    return None


def start(db, room, user_id):
    host_only(room, user_id)
    if room.phase != 'lobby':
        fail(409, 'A session is already in progress.')
    deck = authorized_deck(db, room)
    if not deck:
        fail(422, 'Choose an available deck first.')
    now = utcnow()
    people = members(db, room)
    active = active_lineup(people, now)
    if blocked := readiness(room, active):
        fail(409, blocked)
    if db.scalar(select(func.count()).select_from(StudyRoom)
                 .where(StudyRoom.phase.in_(ACTIVE_PHASES),
                        select(RoomQuestion.position).where(RoomQuestion.session_id == StudyRoom.session_id,
                            RoomQuestion.options.is_(None), RoomQuestion.failed.is_(False)).exists())) >= MAX_PREPARING:
        fail(429, 'Room preparation is busy. Try again shortly.')
    cards = list(db.execute(select(Flashcard.id, Flashcard.front, Flashcard.back).where(Flashcard.deck_id == deck.id)))
    if not cards or len(cards) > 150:
        fail(422, 'Choose a deck with 1–150 cards.')
    random.shuffle(cards)
    players = {str(user.id): identity(user) for _, user in active}
    session = RoomSession(id=str(uuid4()), room_id=room.id, deck_title=deck.title, mode=room.mode,
                          players=players, host_id=room.host_id, total=len(cards))
    db.add(session)
    db.flush()
    db.add_all(RoomQuestion(session_id=session.id, position=position, card_id=card.id,
                            fingerprint=_fingerprint(card.front, card.back))
               for position, card in enumerate(cards))
    room.session_id = session.id
    room.phase = 'preparing'
    for member, user in people:
        member.spectator = str(user.id) not in players
    touch(room)


def lobby_view(db, room, viewer_id):
    now = utcnow()
    deck = authorized_deck(db, room)
    people = members(db, room)
    lineup = active_lineup(people, now)
    guests = [member for member, user in lineup if user.id != room.host_id]
    blockers = readiness(room, lineup) if room.phase == 'lobby' else None
    count, newest = db.execute(select(func.count(),func.max(RoomInvite.created_at)).where(RoomInvite.room_id == room.id)).one()
    return {
        'id': room.id, 'code': room.code, 'name': 'Study Room',
        'phase': room.phase, 'mode': room.mode, 'seconds': room.seconds, 'settings_revision': settings_revision(room),
        'readiness_blocker': blockers, 'readiness': {'ready': sum(member.ready for member in guests), 'total': len(guests)},
        'invite_revision': [count, iso(newest)],
        'is_host': room.host_id == viewer_id, 'share_private': room.share_private, 'capacity': CAPACITY, 'server_time': iso(now),
        'deck': {'id': deck.id, 'title': deck.title,
                 'card_count': db.scalar(select(func.count()).select_from(Flashcard).where(Flashcard.deck_id == deck.id))}
        if deck else None,
        'participants': [{**identity(user), 'host': user.id == room.host_id, 'you': user.id == viewer_id,
                          'ready': member.ready, 'spectator': member.spectator, 'connected': connected(member, now)}
                         for member, user in people],
    }


def chat_view(db, room):
    recent = list(db.scalars(select(RoomMessage).where(RoomMessage.room_id == room.id)
                             .order_by(RoomMessage.id.desc()).limit(80)))
    return [{'id': message.id, 'author': message.author, 'text': message.text,
             'created_at': iso(message.created_at)} for message in reversed(recent)]


def send_message(db, room, user, text):
    now = utcnow()
    recent = db.scalar(select(func.count()).select_from(RoomMessage).where(
        RoomMessage.sender_id == user.id, RoomMessage.created_at > now - timedelta(seconds=10)))
    if recent >= 5:
        fail(429, 'You’re sending messages too quickly. Try again in a few seconds.')
    db.add(RoomMessage(room_id=room.id, sender_id=user.id, author=identity(user), text=text, created_at=now))
    db.flush()
    oldest_kept = select(RoomMessage.id).where(RoomMessage.room_id == room.id).order_by(
        RoomMessage.id.desc()).offset(499).limit(1).scalar_subquery()
    db.execute(delete(RoomMessage).where(RoomMessage.room_id == room.id, RoomMessage.id < oldest_kept))
    touch(room)


def leave(db, room, member):
    db.execute(delete(RoomInvite).where(RoomInvite.room_id == room.id, RoomInvite.sender_id == member.user_id))
    db.delete(member)
    touch(room)


def reset_lobby(db, room):
    room.phase = 'lobby'
    room.session_id = None
    if not authorized_deck(db, room):
        room.deck_id = room.deck_owner_id = None
        room.share_private = False
    for member, _ in members(db, room):
        member.ready = member.spectator = False
    touch(room)


def friends_page(db, room, user_id, page):
    other = case((Friendship.first_id == user_id, Friendship.second_id), else_=Friendship.first_id)
    rows = db.execute(
        select(User, RoomMember.user_id, RoomInvite.user_id).select_from(User)
        .join(Friendship, User.id == other)
        .outerjoin(RoomMember, and_(RoomMember.room_id == room.id, RoomMember.user_id == User.id))
        .outerjoin(RoomInvite, and_(RoomInvite.room_id == room.id, RoomInvite.user_id == User.id))
        .where(Friendship.accepted, or_(Friendship.first_id == user_id, Friendship.second_id == user_id))
        .order_by(User.display_name.collate('NOCASE'), User.username)
        .offset((page - 1) * FRIENDS_PER_PAGE).limit(FRIENDS_PER_PAGE + 1)
    ).all()
    full = len(members(db, room)) >= CAPACITY
    return {'page': page, 'has_next': len(rows) > FRIENDS_PER_PAGE, 'items': [
        {**identity(user), 'status': 'member' if member else 'invited' if invited else 'full' if full else 'available'}
        for user, member, invited in rows[:FRIENDS_PER_PAGE]
    ]}
