from datetime import timezone

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import delete
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth.config import get_settings
from app.auth.dependencies import check_origin, require_user
from app.auth.service import (SESSION_SECONDS, DUMMY_HASH, csrf_token, hash_token,
                              hasher, new_session, normalize_email, reserve_login_attempt, verify_password)
from app.database import get_write_db
from app.models import AuthSession, LoginThrottle, User, utcnow
from sqlalchemy import select

router = APIRouter(prefix='/api/auth', tags=['Authentication'])


def user_view(user, token):
    return {'id':user.id, 'email':user.email, 'csrf_token':csrf_token(token)}


def login_error(status=401, retry=None):
    message = 'Too many login attempts. Try again later.' if status == 429 else 'Invalid email or password.'
    return JSONResponse(status_code=status, content={'error':{'message':message}},
                        headers={'Retry-After':str(retry)} if retry else None)


@router.post('/login')
async def login(request: Request, response: Response, db: Session = Depends(get_write_db)):
    check_origin(request)
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        return login_error()
    # Bounds apply before parsing/hashing; no submitted password is ever logged.
    body = await request.body()
    if len(body) > 16384:
        return login_error()
    try:
        payload = await request.json()
        email = normalize_email(payload.get('email'))
        password = payload.get('password')
        valid = isinstance(password, str) and 1 <= len(password) <= 1024 and set(payload) == {'email', 'password'}
    except (ValueError, AttributeError, TypeError):
        email, password, valid = 'invalid-input', '', False
    retry = reserve_login_attempt(db, email, request.client.host if request.client else 'unknown')
    if retry:
        return login_error(429, retry)
    user = db.scalar(select(User).where(User.email == email)) if valid else None
    verified = await run_in_threadpool(verify_password, user.password_hash if user else DUMMY_HASH, password if valid else 'invalid')
    if user is None or not verified:
        # Return instead of raise: failed-attempt counters must commit.
        return login_error()
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = await run_in_threadpool(hasher.hash, password)
    old = request.cookies.get(get_settings().cookie_name)
    if old:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(old)))
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= utcnow()))
    db.execute(delete(LoginThrottle).where(LoginThrottle.key == f'email:{hash_token(email)}'))
    token, record = new_session(db, user)
    settings = get_settings()
    response.set_cookie(settings.cookie_name, token, max_age=SESSION_SECONDS,
                        expires=record.expires_at.replace(tzinfo=timezone.utc),
                        httponly=True, secure=settings.cookie_secure, samesite='lax', path='/')
    return user_view(user, token)


@router.get('/me')
def me(request: Request, user: User = Depends(require_user)):
    return user_view(user, request.cookies[get_settings().cookie_name])


@router.post('/logout', status_code=204)
def logout(request: Request, response: Response, user: User = Depends(require_user),
           db: Session = Depends(get_write_db)):
    token = request.cookies[get_settings().cookie_name]
    db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    response.delete_cookie(get_settings().cookie_name, path='/', secure=get_settings().cookie_secure,
                           httponly=True, samesite='lax')
