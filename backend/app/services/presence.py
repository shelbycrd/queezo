from datetime import timedelta

from sqlalchemy import exists, select

from app.models import AuthSession, SessionPresence, utcnow


def online_presence(user_id):
    now = utcnow()
    return exists(
        select(AuthSession.token_hash).join(SessionPresence)
        .where(AuthSession.user_id == user_id, AuthSession.expires_at > now,
               SessionPresence.seen_at > now - timedelta(minutes=2))
    )
