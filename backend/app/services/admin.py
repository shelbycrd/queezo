"""Explicit, server-local administrative read and moderation operations."""
from datetime import date
import os
from pathlib import Path
import secrets

import httpx
from sqlalchemy import delete, func, or_, select, text

from app.auth.service import hasher, validate_password
from app.database import write_transaction
from app.models import (
    AdminAudit, AuthSession, Deck, Flashcard, FlashcardDistractorCache, FlashcardDistractorJob,
    MultipleChoiceQuestion, MultipleChoiceSession, ProfileReport, RoomInvite, RoomMember,
    RoomQuestion, RoomSession, StudyRoom, StudySession, User, utcnow,
)
from app.services import distractors, room_study, study_rooms
from app.services.admin_auth import AdminError, normalized_reason, record, verify_principal
from app.services.presenters import iso


def count(db, model, *conditions):
    return db.scalar(select(func.count()).select_from(model).where(*conditions))


def need(row):
    if row is None:
        raise AdminError('Target not found.')
    return row


def find_user(db, username):
    return need(db.scalar(select(User).where(User.username == username)))


def user_view(user):
    return {'username': user.username, 'uid': user.uid, 'display_name': user.display_name,
            'created_at': iso(user.created_at), 'suspended_at': iso(user.suspended_at)}


def deck_view(deck):
    return {'id': deck.id, 'title': deck.title, 'owner_id': deck.owner_id, 'visibility': deck.visibility,
            'unpublished_at': iso(deck.unpublished_at), 'updated_at': iso(deck.updated_at)}


def report_view(report):
    return {'id': report.id, 'target_id': report.target_id, 'reporter_id': report.reporter_id,
            'category': report.reason, 'created_at': iso(report.created_at), 'reviewed_at': iso(report.reviewed_at),
            'status': report.disposition or ('reviewed' if report.reviewed_at else 'pending')}


def room_view(room):
    return {'id': room.id, 'host_id': room.host_id, 'deck_id': room.deck_id, 'session_id': room.session_id,
            'phase': room.phase, 'mode': room.mode, 'updated_at': iso(room.updated_at)}


def audit_view(event):
    return {'id': event.id, 'operator': event.operator, 'action': event.action, 'target': event.target,
            'reason': event.reason, 'outcome': event.outcome, 'timestamp': iso(event.created_at)}


def list_rows(db, model, serialize, args, *conditions):
    return [serialize(row) for row in db.scalars(select(model).where(*conditions)
            .order_by(model.id.desc()).limit(args.limit).offset(args.offset))]


def users_read(db, args):
    if args.action == 'inspect':
        user = find_user(db, args.target)
        return {**user_view(user), 'decks': count(db, Deck, Deck.owner_id == user.id),
                'active_sessions': count(db, AuthSession, AuthSession.user_id == user.id,
                                         AuthSession.expires_at > utcnow())}
    if args.action == 'list':
        # Match the authentication API while email verification is unavailable.
        return list_rows(db, User, lambda user: {
            **user_view(user), 'email': user.email, 'email_verified': False,
        }, args)
    return list_rows(db, User, user_view, args, or_(
        User.username.icontains(args.query, autoescape=True),
        User.display_name.icontains(args.query, autoescape=True),
    ))


def decks_read(db, args):
    if args.action == 'list':
        return list_rows(db, Deck, deck_view, args)
    deck = need(db.get(Deck, args.target))
    return {**deck_view(deck), 'cards': count(db, Flashcard, Flashcard.deck_id == deck.id),
            'classic_sessions': count(db, StudySession, StudySession.deck_id == deck.id),
            'multiple_choice_sessions': count(db, MultipleChoiceSession, MultipleChoiceSession.deck_id == deck.id)}


def reports_read(db, args):
    if args.action == 'list':
        return list_rows(db, ProfileReport, report_view, args)
    report = need(db.get(ProfileReport, args.target))
    return {**report_view(report), 'explanation': report.explanation}


def rooms_read(db, args):
    if args.action == 'list':
        return list_rows(db, StudyRoom, room_view, args)
    room = need(db.get(StudyRoom, args.target))
    session = db.get(RoomSession, room.session_id) if room.session_id else None
    return {**room_view(room), 'participants': [
        {'username': user.username, 'spectator': member.spectator, 'ready': member.ready}
        for member, user in study_rooms.members(db, room)
    ], 'pending_invites': count(db, RoomInvite, RoomInvite.room_id == room.id),
        'result': {'completed_at': iso(session.completed_at), 'standings': room_study.standings(session)}
        if session and session.completed_at else None}


def database_info(db):
    return {'sqlite_version': db.scalar(select(func.sqlite_version())),
            'schema_version': db.scalar(text('PRAGMA user_version')),
            'journal_mode': db.scalar(text('PRAGMA journal_mode')),
            'foreign_keys': bool(db.scalar(text('PRAGMA foreign_keys'))),
            'busy_timeout_ms': db.scalar(text('PRAGMA busy_timeout')),
            'page_bytes': db.scalar(text('PRAGMA page_count')) * db.scalar(text('PRAGMA page_size'))}


def backup_info(db, marker=Path('/backup-status/.last-success')):
    database = db.get_bind().url.database
    snapshots = Path(database).parent / '.migration-backups' / Path(database).name if database else None
    migration_count = sum(path.is_file() for path in snapshots.glob('pre-migration-*.db')) if snapshots else 0
    try:
        verified = date.fromisoformat(marker.read_text(encoding='ascii').strip()[:32]).isoformat()
    except (OSError, ValueError):
        verified = None
    return {'migration_snapshots': migration_count, 'daily_last_success_utc': verified,
            'daily_status': 'reported' if verified else 'unavailable'}


def system_read(db, args):
    if args.action == 'status':
        return {'database': 'reachable', 'schema_version': db.scalar(text('PRAGMA user_version')),
                'console': 'authenticated'}
    if args.action == 'database':
        return database_info(db)
    if args.action == 'backups':
        return backup_info(db)
    return {'users': count(db, User), 'suspended_users': count(db, User, User.suspended_at.is_not(None)),
            'active_sessions': count(db, AuthSession, AuthSession.expires_at > utcnow()),
            'decks': count(db, Deck), 'unpublished_decks': count(db, Deck, Deck.unpublished_at.is_not(None)),
            'cards': count(db, Flashcard), 'open_rooms': count(db, StudyRoom, StudyRoom.phase != 'closed'),
            'pending_reports': count(db, ProfileReport, ProfileReport.reviewed_at.is_(None))}


def ai_status():
    model = distractors.configured_model()
    status = {'configured_model': model, 'reachable': False, 'configured_model_installed': None}
    expected_name = model if ':' in model.rsplit('/', 1)[-1] else f'{model}:latest'
    base_url = os.getenv('OLLAMA_BASE_URL', distractors.DEFAULT_BASE_URL).strip().rstrip('/')
    try:
        url = httpx.URL(f'{base_url}/api/tags')
        if url.scheme not in {'http', 'https'} or not url.host or url.userinfo or url.query or url.fragment:
            return status
        with httpx.Client(timeout=2.0, trust_env=False, follow_redirects=False) as client:
            response = client.get(url)
        response.raise_for_status()
        models = response.json()['models']
        if isinstance(models, list):
            status.update(reachable=True, configured_model_installed=any(
                isinstance(item, dict) and item.get('name') == expected_name for item in models
            ))
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, TypeError):
        pass
    return status


def ai_read(db, args):
    if args.action == 'cache-stats':
        return {'ollama_only': count(db, FlashcardDistractorCache, FlashcardDistractorCache.source == 'ollama'),
                'with_deck_fallback': count(db, FlashcardDistractorCache, FlashcardDistractorCache.source == 'fallback'),
                'unexpired_generation_claims': count(db, FlashcardDistractorJob,
                                                     FlashcardDistractorJob.expires_at > utcnow())}
    return {'solo_sessions': count(db, MultipleChoiceSession),
            'solo_ready_snapshots': count(db, MultipleChoiceQuestion, MultipleChoiceQuestion.correct_option_id.is_not(None)),
            'solo_failed_snapshots': count(db, MultipleChoiceQuestion, MultipleChoiceQuestion.failure.is_not(None)),
            'room_ready_snapshots': count(db, RoomQuestion, RoomQuestion.correct_id.is_not(None)),
            'room_failed_snapshots': count(db, RoomQuestion, RoomQuestion.failed.is_(True))}


def audit_read(db, args):
    if args.action == 'list':
        return list_rows(db, AdminAudit, audit_view, args)
    return audit_view(need(db.get(AdminAudit, args.target)))


def users_change(db, args):
    user = find_user(db, args.target)
    if args.action == 'changepassword':
        # The hash was computed before this transaction; the plaintext never reaches this point.
        if args.password_hash is not None:
            user.password_hash = args.password_hash
        revoked = db.execute(delete(AuthSession).where(AuthSession.user_id == user.id)).rowcount
        return {'password_changed': args.password_hash is not None, 'revoked_sessions': revoked}
    if args.action == 'suspend':
        if user.suspended_at is not None:
            raise AdminError('User is already suspended.')
        user.suspended_at = utcnow()
    elif args.action == 'unsuspend':
        if user.suspended_at is None:
            raise AdminError('User is not suspended.')
        user.suspended_at = None
        return {'suspended': False}
    result = db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    if args.action == 'revoke-sessions' and not result.rowcount:
        raise AdminError('User has no sessions to revoke.')
    return {'revoked_sessions': result.rowcount, 'suspended': user.suspended_at is not None}


def decks_change(db, args):
    deck = need(db.get(Deck, args.target))
    if args.action == 'unpublish':
        if deck.unpublished_at:
            raise AdminError('Deck is already unpublished.')
        if deck.owner_id is None or deck.visibility == 'private':
            raise AdminError('Only a published deck can be unpublished.')
        deck.unpublished_at = utcnow()
        deck.share_token = None
    else:
        if deck.unpublished_at is None:
            raise AdminError('Deck is not unpublished.')
        deck.unpublished_at = None
        deck.share_token = secrets.token_urlsafe(32)
    deck.updated_at = utcnow()
    return {'visibility': deck.visibility, 'unpublished': deck.unpublished_at is not None}


def reports_change(db, args):
    report = need(db.get(ProfileReport, args.target))
    if report.disposition:
        raise AdminError('Report already has a final disposition.')
    report.reviewed_at = report.reviewed_at or utcnow()
    report.disposition = 'resolved' if args.action == 'resolve' else 'dismissed'
    return {'status': report.disposition}


def rooms_change(db, args):
    room = need(db.get(StudyRoom, args.target))
    if room.phase == 'closed':
        raise AdminError('Room is already closed.')
    session = db.get(RoomSession, room.session_id) if room.session_id else None
    if session and room.phase in study_rooms.ACTIVE_PHASES:
        room_study.finish(room, session, utcnow())
    study_rooms.close(db, room)
    return {'phase': 'closed', 'participants': count(db, RoomMember, RoomMember.room_id == room.id)}


READERS = {'users': users_read, 'decks': decks_read, 'reports': reports_read, 'rooms': rooms_read,
           'system': system_read, 'ai': ai_read, 'audit': audit_read}
CHANGES = {'users': users_change, 'decks': decks_change, 'reports': reports_change, 'rooms': rooms_change}


def prepare_password(args):
    """Validate and hash a reset password outside the write transaction, then drop the plaintext."""
    password, args.password, args.password_hash = getattr(args, 'password', None), None, None
    if password is None:
        if args.yes:
            raise AdminError('Enter the new password at the hidden prompt. Nothing was changed.')
        return
    try:
        validate_password(password)
    except ValueError as error:
        raise AdminError(f'{error} Nothing was changed.') from None
    if args.yes:
        args.password_hash = hasher.hash(password)


def execute(factory, principal, args):
    if args.change:
        reason = normalized_reason(args.reason)
        if not (args.yes ^ args.dry_run):
            raise AdminError('Use --yes to confirm or --dry-run to preview.')
        if (args.group, args.action) == ('users', 'changepassword'):
            prepare_password(args)
        error = None
        action = f'{args.group} {args.action}'
        with write_transaction(factory) as db:
            verify_principal(db, principal)
            try:
                with db.begin_nested() as preview:
                    result = CHANGES[args.group](db, args)
                    db.flush()
                    if args.dry_run:
                        preview.rollback()
            except AdminError as rejection:
                error = rejection
            outcome = 'denied' if error else ('dry-run' if args.dry_run else 'success')
            record(db, principal.operator, action, args.target, outcome, reason)
        if error:
            raise error
        return {'mode': outcome, 'action': action, 'target': args.target, **result}
    with factory() as db:
        verify_principal(db, principal)
        if (args.group, args.action) != ('ai', 'status'):
            return READERS[args.group](db, args)
    return ai_status()
