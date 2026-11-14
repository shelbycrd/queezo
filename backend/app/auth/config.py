import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit


@dataclass(frozen=True)
class AuthSettings:
    environment: str
    cookie_secure: bool
    trusted_origins: tuple[str, ...]

    @property
    def cookie_name(self):
        return "__Host-queezo_session" if self.cookie_secure else "queezo_session"


@lru_cache
def get_settings():
    environment = os.getenv("AUTH_ENV", "production").lower()
    if environment not in {"production", "development", "test"}:
        raise ValueError("AUTH_ENV must be production, development, or test.")
    raw = os.getenv("AUTH_COOKIE_SECURE", "true").lower()
    if raw not in {"true", "false"}:
        raise ValueError("AUTH_COOKIE_SECURE must be true or false.")
    secure = raw == "true"
    if environment == "production" and not secure:
        raise ValueError("Production requires AUTH_COOKIE_SECURE=true and HTTPS.")
    origins = tuple(value.strip().rstrip('/') for value in os.getenv("AUTH_TRUSTED_ORIGINS", "").split(',') if value.strip())
    if not origins:
        raise ValueError("Set AUTH_TRUSTED_ORIGINS to the exact browser origin(s), including port.")
    for origin in origins:
        url = urlsplit(origin)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.path or url.query or url.fragment:
            raise ValueError("AUTH_TRUSTED_ORIGINS requires exact HTTP(S) origins, without paths or wildcards.")
        if '*' in origin or (environment == "production" and url.scheme != "https"):
            raise ValueError("Production origins must use HTTPS; wildcard origins are forbidden.")
    return AuthSettings(environment, secure, origins)
