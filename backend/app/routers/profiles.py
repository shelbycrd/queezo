"""Profile presentation, owner preferences, and authenticated reports."""
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import optional_user, require_user
from app.auth.service import normalize_display_name
from app.database import get_db, get_write_db
from app.models import Deck, Flashcard, ProfileAvatarChange, ProfileReport, User, utcnow
from app.services.presenters import iso

router = APIRouter(prefix='/api/profiles', tags=['Profiles'])
INTERESTS = (
    'Programming', 'Mathematics', 'Science', 'History', 'Languages', 'Engineering',
    'Literature', 'Art', 'Music', 'Economics', 'Psychology', 'Geography', 'Business',
)
Avatar = Literal['dog', 'cat', 'chicken', 'duck', 'fox', 'panda', 'cow', 'hamster', 'fish', 'octopus']
Visibility = Literal['public', 'unlisted', 'private']
DeckSort = Literal['newest', 'oldest', 'alphabetical']
ReportReason = Literal['inappropriate_bio', 'impersonation', 'spam', 'other']
NAME_WINDOW = timedelta(days=14)
AVATAR_WINDOW = timedelta(hours=1)
AVATAR_LIMIT = 10
REPORT_WINDOW = timedelta(days=1)
REPORT_LIMIT = 5


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    display_name: str = Field(max_length=80)
    bio: str = Field(max_length=200)
    interest_tags: list[str] = Field(max_length=5)
    avatar: Avatar
    visibility: Visibility
    featured_deck_id: int | None = Field(ge=1)

    @field_validator('display_name')
    @classmethod
    def valid_name(cls, value):
        return normalize_display_name(value)

    @field_validator('interest_tags')
    @classmethod
    def valid_tags(cls, values):
        if any(tag not in INTERESTS for tag in values) or len(set(values)) != len(values):
            raise ValueError('Choose up to five different interests from the list.')
        return values


class ReportInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    reason: ReportReason
    explanation: str = Field(default='', max_length=400)


def public_decks(owner_id):
    return select(Deck).where(Deck.owner_id == owner_id, Deck.visibility == 'public',
                              Deck.share_token.is_not(None))


def deck_summaries(db, statement):
    # Count cards in one grouped query for only the decks in the current page.
    decks = list(db.scalars(statement))
    if not decks:
        return []
    counts = dict(db.execute(select(Flashcard.deck_id, func.count()).where(
        Flashcard.deck_id.in_([deck.id for deck in decks])
    ).group_by(Flashcard.deck_id)).all())
    return [{
        'title': deck.title, 'visibility': 'public', 'share_token': deck.share_token,
        'card_count': counts.get(deck.id, 0),
        'created_at': iso(deck.created_at), 'updated_at': iso(deck.updated_at),
    } for deck in decks]


def profile_for(db, username, viewer_id):
    profile = db.scalar(select(User).where(User.username == username))
    if profile is None or (profile.id != viewer_id and profile.profile_visibility == 'private'):
        raise HTTPException(404, 'Profile not found.')
    return profile


def avatar_times(db, user_id, now):
    return list(db.scalars(select(ProfileAvatarChange.changed_at).where(
        ProfileAvatarChange.user_id == user_id,
        ProfileAvatarChange.changed_at > now - AVATAR_WINDOW,
    ).order_by(ProfileAvatarChange.changed_at)))


def name_date(profile):
    return profile.display_name_changed_at + NAME_WINDOW if profile.display_name_changed_at else None


def profile_view(db, profile, owner):
    featured = deck_summaries(db, public_decks(profile.id).where(Deck.id == profile.featured_deck_id)) if profile.featured_deck_id else []
    view = {
        'username': profile.username, 'display_name': profile.display_name,
        'joined_at': iso(profile.created_at), 'bio': profile.bio,
        'interest_tags': profile.interest_tags, 'avatar': profile.avatar,
        'is_owner': owner, 'featured_deck': featured[0] if featured else None,
    }
    if owner:
        changes = avatar_times(db, profile.id, utcnow())
        view.update({
            'visibility': profile.profile_visibility,
            'interests': INTERESTS,
            'display_name_next_change_at': iso(name_date(profile)),
            'avatar_changes_remaining': max(0, AVATAR_LIMIT - len(changes)),
            'avatar_next_change_at': iso(changes[0] + AVATAR_WINDOW) if len(changes) >= AVATAR_LIMIT else None,
            'featured_deck_id': profile.featured_deck_id if featured else None,
        })
    return view


@router.get('/me')
def own_profile(user: User = Depends(require_user), db: Session = Depends(get_db)):
    return profile_view(db, user, True)


@router.get('/me/featured-options')
def featured_options(user: User = Depends(require_user), db: Session = Depends(get_db)):
    statement = public_decks(user.id).with_only_columns(Deck.id, Deck.title)
    return [dict(row) for row in db.execute(statement.order_by(Deck.title.collate('NOCASE'), Deck.id)).mappings()]


@router.patch('/me')
def update_profile(body: ProfileUpdate, user: User = Depends(require_user), db: Session = Depends(get_write_db)):
    profile = db.get(User, user.id)
    now = utcnow()
    name_changed = body.display_name != profile.display_name
    avatar_changed = body.avatar != profile.avatar
    next_name = name_date(profile)
    if name_changed and next_name and next_name > now:
        raise HTTPException(429, 'Your display name can change once every 14 days.')
    if avatar_changed:
        if len(avatar_times(db, profile.id, now)) >= AVATAR_LIMIT:
            raise HTTPException(429, 'You can change your avatar 10 times per hour.')
    if body.featured_deck_id is not None and db.scalar(public_decks(profile.id).with_only_columns(
            Deck.id).where(Deck.id == body.featured_deck_id)) is None:
        raise HTTPException(422, 'Choose one of your public decks to feature.')
    if name_changed:
        profile.display_name = body.display_name
        profile.display_name_changed_at = now
    if avatar_changed:
        db.execute(delete(ProfileAvatarChange).where(ProfileAvatarChange.user_id == profile.id,
                                                    ProfileAvatarChange.changed_at <= now - AVATAR_WINDOW))
        db.add(ProfileAvatarChange(user_id=profile.id, changed_at=now))
        profile.avatar = body.avatar
    profile.bio = body.bio
    profile.interest_tags = body.interest_tags
    profile.profile_visibility = body.visibility
    profile.featured_deck_id = body.featured_deck_id
    db.flush()
    return profile_view(db, profile, True)


@router.get('/search')
def discover(q: str = Query('', max_length=80), db: Session = Depends(get_db)):
    term = q.strip().lower()
    statement = select(User.username, User.display_name, User.avatar).where(User.profile_visibility == 'public')
    if term:
        statement = statement.where(User.username.contains(term, autoescape=True) |
                                    func.lower(User.display_name).contains(term, autoescape=True))
    return [dict(row) for row in db.execute(statement.order_by(User.username).limit(25)).mappings()]


@router.get('/users/{username}')
def read_profile(username: str, viewer: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    viewer_id = viewer.id if viewer else None
    profile = profile_for(db, username, viewer_id)
    return profile_view(db, profile, profile.id == viewer_id)


@router.get('/users/{username}/decks')
def list_profile_decks(
    username: str, q: str = Query('', max_length=120), sort: DeckSort = 'newest',
    page: int = Query(1, ge=1, le=100000), limit: int = Query(12, ge=1, le=48),
    viewer: User | None = Depends(optional_user), db: Session = Depends(get_db),
):
    profile = profile_for(db, username, viewer.id if viewer else None)
    statement = public_decks(profile.id)
    if profile.featured_deck_id is not None:
        statement = statement.where(Deck.id != profile.featured_deck_id)
    if q.strip():
        statement = statement.where(func.lower(Deck.title).contains(q.strip().lower(), autoescape=True))
    sort_keys = {
        'newest': (Deck.created_at.desc(), Deck.id.desc()),
        'oldest': (Deck.created_at.asc(), Deck.id.asc()),
        'alphabetical': (Deck.title.collate('NOCASE'), Deck.id.asc()),
    }
    items = deck_summaries(db, statement.order_by(*sort_keys[sort]).offset((page - 1) * limit).limit(limit + 1))
    return {'items': items[:limit], 'has_more': len(items) > limit}


@router.post('/users/{username}/reports', status_code=204)
def report_profile(username: str, body: ReportInput, user: User = Depends(require_user),
                   db: Session = Depends(get_write_db)):
    target = profile_for(db, username, user.id)
    if target.id == user.id:
        raise HTTPException(422, 'You cannot report your own profile.')
    now = utcnow()
    recent = select(ProfileReport.target_id).where(
        ProfileReport.reporter_id == user.id, ProfileReport.created_at > now - REPORT_WINDOW,
    )
    targets = set(db.scalars(recent))
    if target.id in targets:
        raise HTTPException(429, 'You already reported this profile in the last 24 hours.')
    if len(targets) >= REPORT_LIMIT:
        raise HTTPException(429, 'You can submit up to five profile reports in 24 hours.')
    db.add(ProfileReport(target_id=target.id, reporter_id=user.id, reason=body.reason,
                         explanation=body.explanation, created_at=now))
