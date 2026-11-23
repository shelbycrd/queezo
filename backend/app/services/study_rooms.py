"""Membership and lobby operations for private multiplayer study rooms."""

import random
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, func, select

from app.models import Deck, Flashcard, Friendship, RoomInvite, RoomMember, RoomMessage, RoomQuestion, RoomSession, StudyRoom, User, utcnow
from app.services.distractor_cache import _fingerprint
from app.services.presenters import iso

CAPACITY = 6
MAX_OPEN_ROOMS = 3
MAX_ROOMS = 100
MAX_PREPARING = 8
GRACE = timedelta(seconds=45)
IDLE = timedelta(minutes=30)
HEARTBEAT = timedelta(seconds=20)


def fail(status, message):
    raise HTTPException(status, message)


def identity(user):
    return {'username': user.username, 'display_name': user.display_name, 'avatar': user.avatar}


def membership(db, room_id, user_id):
    room = db.get(StudyRoom, room_id)
    member = db.get(RoomMember, (room_id, user_id)) if room else None
    if not room or not member or room.phase == 'closed':
        fail(404, 'Study room not found.')
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


def invite(db, room, sender_id, username):
    other = eligible_friend(db, sender_id, username)
    if len(members(db, room)) >= CAPACITY:
        fail(409, 'This room is full.')
    if db.get(RoomMember, (room.id, other.id)):
        fail(409, 'That friend is already in the room.')
    if not db.get(RoomInvite, (room.id, other.id)):
        db.add(RoomInvite(room_id=room.id, user_id=other.id, sender_id=sender_id))
        touch(room)


def create(db, user_id, username):
    if db.scalar(select(func.count()).select_from(StudyRoom)
                 .where(StudyRoom.host_id == user_id, StudyRoom.phase != 'closed')) >= MAX_OPEN_ROOMS:
        fail(429, 'Close an existing room before creating another.')
    if db.scalar(select(func.count()).select_from(StudyRoom).where(StudyRoom.phase != 'closed')) >= MAX_ROOMS:
        fail(429, 'Study rooms are busy. Try again later.')
    room = StudyRoom(id=str(uuid4()), host_id=user_id)
    db.add(room)
    db.flush()
    db.add(RoomMember(room_id=room.id, user_id=user_id, seen_at=utcnow()))
    db.flush()
    invite(db, room, user_id, username)
    return room.id


def invitations(db, user_id):
    rows = db.execute(select(RoomInvite, User).join(User, User.id == RoomInvite.sender_id)
                      .join(StudyRoom, StudyRoom.id == RoomInvite.room_id)
                      .where(RoomInvite.user_id == user_id, StudyRoom.phase != 'closed')
                      .order_by(RoomInvite.created_at.desc()))
    return [{'room_id': row.room_id, 'sender': identity(sender), 'sent_at': iso(row.created_at)}
            for row, sender in rows]


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
    if not deck or deck.owner_id != room.deck_owner_id:
        return None
    if deck.visibility == 'public':
        return deck
    if room.share_private and db.get(RoomMember, (room.id, deck.owner_id)):
        return deck
    return None


def configure(db, room, user_id, settings):
    host_only(room, user_id)
    if room.phase != 'lobby':
        fail(409, 'Return to the lobby before changing settings.')
    deck = db.get(Deck, settings.deck_id) if settings.deck_id is not None else None
    if settings.deck_id is not None and (not deck or deck.owner_id is None or
            (deck.owner_id != user_id and deck.visibility != 'public')):
        fail(404, 'Deck not available.')
    if deck and deck.visibility != 'public' and not settings.share_private:
        fail(422, 'Authorize sharing this deck with invited room members first.')
    next_settings = (settings.deck_id, settings.mode, settings.seconds, bool(deck and deck.owner_id == user_id and settings.share_private))
    if (room.deck_id, room.mode, room.seconds, room.share_private) != next_settings:
        for member, _ in members(db, room):
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


def start(db, room, user_id):
    host_only(room, user_id)
    if room.phase != 'lobby':
        fail(409, 'A session is already in progress.')
    deck = authorized_deck(db, room)
    if not deck:
        fail(422, 'Choose an available deck first.')
    now = utcnow()
    active = [(member, user) for member, user in members(db, room) if not member.spectator and connected(member, now)]
    if len(active) < 2 or not all(member.ready for member, user in active if user.id != user_id):
        fail(409, 'Two active participants are required. Everyone except the host must be ready.')
    if db.scalar(select(func.count()).select_from(StudyRoom).where(StudyRoom.phase == 'preparing')) >= MAX_PREPARING:
        fail(429, 'Room preparation is busy. Try again shortly.')
    cards = list(db.execute(select(Flashcard.id, Flashcard.front, Flashcard.back).where(Flashcard.deck_id == deck.id)))
    if not cards or len(cards) > 150:
        fail(422, 'Choose a deck with 1–150 cards.')
    random.shuffle(cards)
    players = {str(user.id): identity(user) for _, user in active}
    session = RoomSession(id=str(uuid4()), room_id=room.id, deck_title=deck.title, mode=room.mode,
                          players=players, total=len(cards))
    db.add(session)
    db.flush()
    db.add_all(RoomQuestion(session_id=session.id, position=position, card_id=card.id,
                            fingerprint=_fingerprint(card.front, card.back))
               for position, card in enumerate(cards))
    room.session_id = session.id
    room.phase = 'preparing'
    for member, user in members(db, room):
        member.spectator = str(user.id) not in players
    touch(room)


def lobby_view(db, room, viewer_id):
    now = utcnow()
    deck = authorized_deck(db, room)
    return {
        'id': room.id, 'code': room.id[:8].upper(), 'name': 'Study Room',
        'phase': room.phase, 'mode': room.mode, 'seconds': room.seconds,
        'is_host': room.host_id == viewer_id, 'share_private': room.share_private, 'capacity': CAPACITY, 'server_time': iso(now),
        'deck': {'id': deck.id, 'title': deck.title,
                 'card_count': db.scalar(select(func.count()).select_from(Flashcard).where(Flashcard.deck_id == deck.id))}
        if deck else None,
        'participants': [{**identity(user), 'host': user.id == room.host_id, 'you': user.id == viewer_id,
                          'ready': member.ready, 'spectator': member.spectator, 'connected': connected(member, now)}
                         for member, user in members(db, room)],
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
