import hmac

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.config import get_settings
from app.auth.service import csrf_token, hash_token
from app.database import get_db
from app.models import AuthSession, User, utcnow


def check_origin(request):
    origin = request.headers.get('origin')
    if origin is not None and origin not in get_settings().trusted_origins:
        raise HTTPException(403, "Request origin is not allowed.")
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, "Cross-site requests are not allowed.")


def optional_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(get_settings().cookie_name, '')
    if not 40 <= len(token) <= 128:
        return None
    result = db.execute(select(User, AuthSession).join(AuthSession, AuthSession.user_id == User.id).where(
        AuthSession.token_hash == hash_token(token), AuthSession.expires_at > utcnow(),
        User.suspended_at.is_(None))).first()
    if result is None:
        return None
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        check_origin(request)
        submitted = request.headers.get('x-csrf-token', '')
        if not hmac.compare_digest(submitted.encode(), csrf_token(token).encode()):
            raise HTTPException(403, "Security check failed. Refresh and try again.")
    request.state.auth_session = result[1]
    return result[0]


def require_user(user: User | None = Depends(optional_user)):
    if user is None:
        raise HTTPException(401, "Please log in to continue.")
    return user
