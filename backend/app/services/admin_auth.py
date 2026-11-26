"""Server-local administrator credentials and transactional audit events."""
from dataclasses import dataclass

from app.auth.service import DUMMY_HASH, hasher, reserve_account_action, verify_password
from app.database import write_transaction
from app.models import AdminAudit, AdminCredential, LoginThrottle


ADMIN_ID = 1
LOGIN_BUCKET = 'admin-console-login'
LOGIN_LIMIT = 5


class AdminError(ValueError):
    """A fixed, operator-safe message."""


@dataclass(frozen=True)
class Principal:
    operator: str
    revision: int


def record(db, operator, action, target, outcome, reason=None):
    db.add(AdminAudit(operator=operator, action=action, target=str(target),
                      reason=reason, outcome=outcome))


def normalized_reason(reason):
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 240 or not reason.isprintable():
        raise AdminError('Provide a printable reason of 1–240 characters.')
    return reason.strip()


def current_credential(factory):
    with factory() as db:
        return db.get(AdminCredential, ADMIN_ID)


def verify_principal(db, principal):
    credential = db.get(AdminCredential, ADMIN_ID)
    if not principal or not credential or (credential.operator, credential.revision) != (
        principal.operator, principal.revision,
    ):
        raise AdminError('Administrator authentication expired. Sign in again.')
    return credential


def authenticate(factory, password):
    with write_transaction(factory) as db:
        credential = db.get(AdminCredential, ADMIN_ID)
        if credential is None:
            raise AdminError('Administrator credential is not configured. Run admin setup.')
        retry = reserve_account_action(db, LOGIN_BUCKET, LOGIN_LIMIT)
        if retry:
            raise AdminError(f'Too many administrator login attempts. Try again in {retry} seconds.')
        db.flush()
        bucket = db.get(LoginThrottle, LOGIN_BUCKET)
        reservation = bucket.window_started, bucket.attempts
    valid_length = isinstance(password, str) and 1 <= len(password) <= 1024
    verified = verify_password(credential.password_hash if valid_length else DUMMY_HASH,
                               password if valid_length else 'invalid')
    principal = Principal(credential.operator, credential.revision)
    with write_transaction(factory) as db:
        verify_principal(db, principal)
        record(db, principal.operator, 'auth login', 'console', 'success' if verified and valid_length else 'denied')
        if verified and valid_length:
            bucket = db.get(LoginThrottle, LOGIN_BUCKET)
            if bucket and (bucket.window_started, bucket.attempts) == reservation:
                db.delete(bucket)
            return principal
    raise AdminError('Administrator authentication failed.')


def set_password(factory, mode, password, *, operator=None, principal=None, expected=None, reason=None):
    if not isinstance(password, str) or not 16 <= len(password) <= 1024 or not password.strip():
        raise AdminError('Use a dedicated administrator password of 16–1024 characters.')
    if mode == 'recover':
        reason = normalized_reason(reason)
    if mode in {'rotate', 'recover'} and expected and verify_password(expected.password_hash, password):
        raise AdminError('Choose a different administrator password.')
    encoded = hasher.hash(password)
    with write_transaction(factory) as db:
        credential = db.get(AdminCredential, ADMIN_ID)
        if mode == 'setup':
            if credential:
                raise AdminError('Administrator is already configured. Use admin rotate or admin recover.')
            db.add(AdminCredential(id=ADMIN_ID, operator=operator, password_hash=encoded, revision=1))
        elif mode in {'rotate', 'recover'}:
            if mode == 'rotate':
                verify_principal(db, principal)
            if not credential or not expected or credential.revision != expected.revision:
                raise AdminError('Administrator credential changed or is missing. Restart the command.')
            operator = credential.operator
            credential.password_hash = encoded
            credential.revision += 1
        else:
            raise AdminError('Unknown credential operation.')
        bucket = db.get(LoginThrottle, LOGIN_BUCKET)
        if bucket:
            db.delete(bucket)
        record(db, 'server-root' if mode == 'recover' else operator,
               f'auth {mode}', operator, 'success', reason)
