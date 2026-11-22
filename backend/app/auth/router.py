from datetime import timezone

from anyio import WouldBlock
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth.config import get_settings
from app.auth.dependencies import check_origin, require_user
from app.auth.service import (SESSION_SECONDS, DUMMY_HASH, csrf_token, hash_token,
                              hasher, insert_user, new_session, normalize_email, reserve_login_attempt,
                              verify_password, reserve_signup_attempt, normalize_username,
                              normalize_display_name, validate_password)
from app.database import get_db_factory, get_write_db, write_transaction
from app.models import AuthSession, LoginThrottle, User, utcnow

router = APIRouter(prefix='/api/auth', tags=['Authentication'])


def user_view(user, token):
    return {'id':user.id, 'uid':user.uid, 'username':user.username, 'display_name':user.display_name,
            'email':user.email, 'csrf_token':csrf_token(token)}


def error(message, status, retry=None):
    return JSONResponse(status_code=status, content={'error':{'message':message}},
                        headers={'Retry-After':str(retry)} if retry else None)


def login_error(status=401, retry=None):
    message = 'Too many login attempts. Try again later.' if status == 429 else 'Invalid email or password.'
    return error(message, status, retry)


def rotate_session(db, user, old):
    if old and 40 <= len(old) <= 128:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(old)))
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= utcnow()))
    token, record = new_session(db, user)
    return user_view(user, token), token, record.expires_at


async def authenticate(request, response, operation, factory, payload):
    settings = get_settings()
    slots = request.app.state.auth_slots
    try:
        slots.acquire_nowait()
    except WouldBlock:
        return error('Authentication is busy. Try again shortly.', 429, 1)
    try:
        result = await run_in_threadpool(
            operation, factory, payload, request.client.host if request.client else 'unknown',
            request.cookies.get(settings.cookie_name),
        )
    finally:
        slots.release()
    if isinstance(result, Response):
        return result
    user, token, expires = result
    response.set_cookie(settings.cookie_name, token, max_age=SESSION_SECONDS,
                        expires=expires.replace(tzinfo=timezone.utc),
                        httponly=True, secure=settings.cookie_secure, samesite='lax', path='/')
    return user


def signup_account(factory, payload, address, old):
    with write_transaction(factory) as db:
        retry = reserve_signup_attempt(db, address)
    if retry:
        return error('Too many sign-up attempts. Try again later.', 429, retry)
    if payload is None:
        return error('Send the sign-up form as JSON.', 422)
    try:
        if not isinstance(payload, dict) or set(payload) != {'display_name','username','email','password','confirm_password'}:
            raise ValueError('Complete all five account fields.')
        password = validate_password(payload['password'])
        if password != payload['confirm_password']:
            raise ValueError('Passwords do not match.')
        email = normalize_email(payload['email'])
        username = normalize_username(payload['username'])
        name = normalize_display_name(payload['display_name'])
    except ValueError as exc:
        return error(str(exc), 422)

    password_hash = hasher.hash(password)
    with write_transaction(factory) as db:
        try:
            user = insert_user(db, email, username, name, password_hash)
        except ValueError:
            return error('An account with those details already exists.', 409)
        return rotate_session(db, user, old)


def login_account(factory, payload, address, old):
    try:
        email = normalize_email(payload.get('email'))
        password = payload.get('password')
        valid = isinstance(password, str) and 1 <= len(password) <= 1024 and set(payload) == {'email', 'password'}
    except (ValueError, AttributeError, TypeError):
        email, password, valid = 'invalid-input', '', False

    bucket_key = f'email:{hash_token(email)}'
    with write_transaction(factory) as db:
        retry = reserve_login_attempt(db, email, address)
        if retry:
            return login_error(429, retry)
        db.flush()
        bucket = db.get(LoginThrottle, bucket_key)
        reservation = bucket.window_started, bucket.attempts
        credential = db.execute(select(User.id, User.uid, User.password_hash).where(User.email == email)).one_or_none() if valid else None

    stored_hash = credential.password_hash if credential else DUMMY_HASH
    verified = verify_password(stored_hash, password if valid else 'invalid')
    if not credential or not verified:
        return login_error()
    replacement = hasher.hash(password) if hasher.check_needs_rehash(stored_hash) else None

    with write_transaction(factory) as db:
        user = db.get(User, credential.id)
        # Deletion, identity reuse and credential changes must invalidate this verification.
        if not user or user.uid != credential.uid or user.email != email or user.password_hash != stored_hash:
            return login_error()
        if replacement:
            user.password_hash = replacement
        # A successful login must not erase unrelated attempts reserved during verification.
        bucket = db.get(LoginThrottle, bucket_key)
        if bucket and (bucket.window_started, bucket.attempts) == reservation:
            db.delete(bucket)
        return rotate_session(db, user, old)


async def read_json(request):
    if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
        return None
    try:
        payload = await request.json()
        return {} if payload is None else payload
    except ValueError:
        return {}


@router.post('/signup', status_code=201)
async def signup(request: Request, response: Response, factory=Depends(get_db_factory)):
    check_origin(request)
    if not get_settings().public_signup:
        return error('Public sign-up is closed. Contact the Queezo operator for an account.', 403)
    return await authenticate(request, response, signup_account, factory, await read_json(request))


@router.post('/login')
async def login(request: Request, response: Response, factory=Depends(get_db_factory)):
    check_origin(request)
    payload = await read_json(request)
    if payload is None:
        return login_error()
    return await authenticate(request, response, login_account, factory, payload)


@router.get('/me')
def me(request: Request, user: User = Depends(require_user)):
    return user_view(user, request.cookies[get_settings().cookie_name])


@router.post('/logout', status_code=204)
def logout(request: Request, response: Response, user: User = Depends(require_user),
           db: Session = Depends(get_write_db, scope="function")):
    token = request.cookies[get_settings().cookie_name]
    db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    response.delete_cookie(get_settings().cookie_name, path='/', secure=get_settings().cookie_secure,
                           httponly=True, samesite='lax')
