from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, exists, or_, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.auth.dependencies import require_user
from app.auth.service import normalize_username, reserve_account_action
from app.database import get_db, get_write_db
from app.models import AuthSession, Deck, Friendship, SessionPresence, User, utcnow
from app.routers.profiles import deck_summaries, public_decks

router = APIRouter(prefix='/api/friends', tags=['Friends'])


class FriendRequest(BaseModel):
    username: str = Field(max_length=32)


class FriendResponse(BaseModel):
    decision: Literal['accept', 'decline']


def request_error(message, status, retry=None):
    return JSONResponse({'error': {'message': message}}, status_code=status,
                        headers={'Retry-After': str(retry)} if retry else None)


def identity(user):
    return {'username': user.username, 'display_name': user.display_name}


@router.get('')
def list_friends(user: User = Depends(require_user), db: Session = Depends(get_db)):
    now = utcnow()
    online = exists(
        select(AuthSession.token_hash).join(SessionPresence)
        .where(AuthSession.user_id == User.id, AuthSession.expires_at > now,
               SessionPresence.seen_at > now - timedelta(minutes=2))
    )
    other_id = case((Friendship.first_id == user.id, Friendship.second_id), else_=Friendship.first_id)
    rows = db.execute(
        select(Friendship, User, online.label('online')).join(User, User.id == other_id)
        .where(or_(Friendship.first_id == user.id, Friendship.second_id == user.id))
        .order_by(User.display_name.collate('NOCASE'), User.username)
    )
    result = {'friends': [], 'incoming': [], 'outgoing': []}
    for connection, other, is_online in rows:
        if connection.accepted:
            result['friends'].append({**identity(other), 'online': is_online})
        else:
            key = 'outgoing' if connection.requester_id == user.id else 'incoming'
            result[key].append(identity(other))
    return result


@router.post('/presence', status_code=204)
def mark_presence(request: Request, user: User = Depends(require_user),
                  db: Session = Depends(get_write_db, scope="function")):
    session_hash = request.state.auth_session.token_hash
    now = utcnow()
    # A session may be revoked between authentication and acquiring the write lock.
    if db.get(AuthSession, session_hash) is not None:
        statement = insert(SessionPresence).values(session_hash=session_hash, seen_at=now)
        db.execute(statement.on_conflict_do_update(
            index_elements=[SessionPresence.session_hash], set_={'seen_at': now}))


@router.post('/requests', status_code=204)
def request_friend(body: FriendRequest, user: User = Depends(require_user),
                   db: Session = Depends(get_write_db, scope="function")):
    try:
        username = normalize_username(body.username)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    retry = reserve_account_action(db, f'friend-request:{user.id}', 20)
    if retry:
        return request_error('Too many friend requests. Try again later.', 429, retry)
    other = db.scalar(select(User).where(User.username == username))
    if other is None:
        return request_error('No account has that username.', 404)
    if other.id == user.id:
        raise HTTPException(422, 'Enter someone else’s username.')
    pair = tuple(sorted((user.id, other.id)))
    connection = db.get(Friendship, pair)
    if connection:
        if connection.accepted:
            raise HTTPException(409, 'You are already friends.')
        if connection.requester_id != user.id:
            raise HTTPException(409, 'This person already sent you a request.')
        return
    retry = reserve_account_action(db, f'friend-pair:{user.id}:{other.id}', 1)
    if retry:
        return request_error('Wait before sending another request to this person.', 429, retry)
    db.add(Friendship(first_id=pair[0], second_id=pair[1], requester_id=user.id))


@router.post('/requests/{username}/respond', status_code=204)
def respond(username: str, body: FriendResponse, user: User = Depends(require_user),
            db: Session = Depends(get_write_db, scope="function")):
    other = db.scalar(select(User).where(User.username == username))
    connection = db.get(Friendship, tuple(sorted((user.id, other.id)))) if other else None
    if not connection or connection.accepted or connection.requester_id == user.id:
        raise HTTPException(404, 'Friend request not found.')
    if body.decision == 'accept':
        connection.accepted = True
    else:
        db.delete(connection)


@router.get('/{username}/profile')
def friend_profile(username: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    other = db.scalar(select(User).where(User.username == username))
    connection = db.get(Friendship, tuple(sorted((user.id, other.id)))) if other else None
    if not connection or not connection.accepted or other.profile_visibility == 'private':
        raise HTTPException(404, 'Friend profile not found.')
    decks = public_decks(other.id).order_by(Deck.created_at.desc(), Deck.id.desc())
    return {**identity(other), 'public_decks': deck_summaries(db, decks)}
