from datetime import timedelta
import hashlib
import hmac
import secrets
import re

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import delete, select

from app.models import AuthSession, LoginThrottle, User, utcnow

SESSION_SECONDS = 7 * 24 * 60 * 60
RATE_WINDOW_SECONDS = 15 * 60
hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, type=Type.ID)
# Equal-cost verification for nonexistent accounts; this random value is not a credential.
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def normalize_email(email):
    if not isinstance(email, str) or len(email) > 320:
        raise ValueError("Enter a valid email address.")
    try:
        return validate_email(email.strip(), check_deliverability=False).normalized.casefold()
    except EmailNotValidError as exc:
        raise ValueError("Enter a valid email address.") from exc


def validate_password(password):
    if not isinstance(password, str) or len(password) < 11 or len(password) > 1024:
        raise ValueError("Passwords must contain 11–1024 characters.")
    return password


def verify_password(encoded_hash, password):
    try:
        return hasher.verify(encoded_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def normalize_username(username):
    if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_]{3,32}', username.strip()):
        raise ValueError('Username must contain 3–32 letters, numbers, or underscores.')
    return username.strip().lower()


def normalize_display_name(name):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(c) < 32 for c in name):
        raise ValueError('Display name must contain 1–80 characters.')
    return name.strip()


def create_user(db, email, password, *, username=None, display_name=None):
    email = normalize_email(email)
    validate_password(password)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise ValueError("An account with that email already exists.")
    username = normalize_username(username) if username is not None else 'user_' + secrets.token_hex(10)
    name = normalize_display_name(display_name) if display_name is not None else email.split('@')[0][:80]
    if db.scalar(select(User.id).where(User.username == username)) is not None:
        raise ValueError('An account with that username already exists.')
    user = User(email=email, username=username, display_name=name, password_hash=hasher.hash(password))
    db.add(user)
    db.flush()
    return user


def reserve_signup_attempt(db, address):
    now = utcnow()
    db.execute(delete(LoginThrottle).where(LoginThrottle.window_started <= now - timedelta(seconds=RATE_WINDOW_SECONDS)))
    key = 'signup-ip:' + hash_token(address)
    bucket = db.get(LoginThrottle, key)
    if bucket is None:
        bucket = LoginThrottle(key=key, window_started=now, attempts=0)
        db.add(bucket)
    if bucket.attempts >= 10:
        return max(1, RATE_WINDOW_SECONDS - int((now - bucket.window_started).total_seconds()))
    bucket.attempts += 1
    return 0


def hash_token(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def csrf_token(token):
    # A session-bound synchronizer token, recoverable on /me without persisting
    # the raw session secret. It is not an authentication bearer token.
    return hmac.new(token.encode('utf-8'), b'queezo-csrf-v1', hashlib.sha256).hexdigest()


def new_session(db, user):
    token = secrets.token_urlsafe(32)
    now = utcnow()
    record = AuthSession(token_hash=hash_token(token), user_id=user.id,
                         created_at=now, expires_at=now + timedelta(seconds=SESSION_SECONDS))
    db.add(record)
    db.flush()
    return token, record


def reserve_login_attempt(db, email, address):
    now = utcnow()
    db.execute(delete(LoginThrottle).where(
        LoginThrottle.window_started <= now - timedelta(seconds=RATE_WINDOW_SECONDS)))
    # Store only hashes of the email and client address in limiter buckets.
    keys = [(f'ip:{hash_token(address)}', 30), (f'email:{hash_token(email)}', 5)]
    buckets = []
    for key, limit in keys:
        bucket = db.get(LoginThrottle, key)
        if bucket is None:
            bucket = LoginThrottle(key=key, window_started=now, attempts=0)
            db.add(bucket)
        if (now - bucket.window_started).total_seconds() >= RATE_WINDOW_SECONDS:
            bucket.window_started = now
            bucket.attempts = 0
        if bucket.attempts >= limit:
            # In particular, a blocked IP must not create unlimited new email
            # buckets just by changing the submitted address on each request.
            return max(1, RATE_WINDOW_SECONDS - int((now - bucket.window_started).total_seconds()))
        buckets.append((bucket, limit))
    for bucket, _ in buckets:
        bucket.attempts += 1
    return 0
