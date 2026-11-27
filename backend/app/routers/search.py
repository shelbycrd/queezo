"""Global search across public decks, the signed-in user's own decks, and public profiles.

Visibility is decided here, never by the client: other people's private or unlisted decks and private or
unlisted profiles are not searchable, and the viewer's own decks are matched only by the viewer's own id.
"""
import re
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_user
from app.database import get_db
from app.models import Deck, Flashcard, User

router = APIRouter(prefix='/api/search', tags=['Global search'])

SearchType = Literal['all', 'public', 'mine', 'users']
SUMMARY_LIMIT = 5   # Per category on the "All" tab.
PAGE_LIMIT = 12     # Default per page on a single category tab.
MAX_LIMIT = 30
MAX_RECENT = 10
REF = re.compile(r'^(?:deck:\d{1,12}|shared:[A-Za-z0-9_-]{32,64}|user:[A-Za-z0-9_]{3,32})$')


def clean_term(raw):
    # Collapse whitespace and drop control characters; matching is a case-insensitive substring test.
    return ' '.join(''.join(ch for ch in raw if ch.isprintable() or ch.isspace()).split())[:80].lower()


def deck_items(db, decks, scope):
    ids = [deck.id for deck in decks]
    counts = dict(db.execute(select(Flashcard.deck_id, func.count()).where(Flashcard.deck_id.in_(ids))
                             .group_by(Flashcard.deck_id)).all()) if ids else {}
    owners = {}
    if scope == 'public' and decks:
        # Show the author only when their profile is publicly discoverable.
        owners = {user.id: user for user in db.scalars(select(User).where(
            User.id.in_({deck.owner_id for deck in decks}), User.profile_visibility == 'public'))}
    items = []
    for deck in decks:
        item = {'kind': 'deck', 'scope': scope, 'title': deck.title, 'card_count': counts.get(deck.id, 0),
                'visibility': deck.visibility if scope == 'mine' else 'public'}
        if scope == 'mine':
            item.update(id=deck.id, path=f'/deck/{deck.id}', ref=f'deck:{deck.id}')
        else:
            owner = owners.get(deck.owner_id)
            item.update(path=f'/shared/{deck.share_token}', ref=f'shared:{deck.share_token}',
                        owner={'username': owner.username, 'display_name': owner.display_name,
                               'avatar': owner.avatar} if owner else None)
        items.append(item)
    return items


def user_item(user):
    return {'kind': 'user', 'username': user.username, 'display_name': user.display_name, 'avatar': user.avatar,
            'path': f'/u/{user.username}', 'ref': f'user:{user.username}'}


def page_of(db, statement, term, offset, limit, build):
    rows = list(db.scalars(statement.offset(offset).limit(limit + 1)))
    return {'items': build(db, rows[:limit]), 'has_more': len(rows) > limit}


def ranked_title(term):
    # Titles that start with the term come first, then newest.
    return [func.lower(Deck.title).startswith(term, autoescape=True).desc(), Deck.created_at.desc(), Deck.id.desc()]


@router.get('')
def search(q: str = Query('', max_length=200), type: SearchType = 'all',
           page: int = Query(1, ge=1, le=1000), limit: int | None = Query(None, ge=1, le=MAX_LIMIT),
           user: User = Depends(require_user), db: Session = Depends(get_db)):
    term = clean_term(q)
    single = type != 'all'
    size = limit or (PAGE_LIMIT if single else SUMMARY_LIMIT)
    offset = (page - 1) * size if single else 0
    result = {'query': term, 'type': type, 'page': page if single else 1}
    empty = {'items': [], 'has_more': False}
    wanted = {'public', 'mine', 'users'} if type == 'all' else {type}
    if not term:
        return {**result, **{section: empty for section in ('public_decks', 'my_decks', 'users')}}

    if 'public' in wanted:
        # Same rules as the community list. Your own decks are reported under My Decks instead.
        statement = select(Deck).where(
            Deck.visibility == 'public', Deck.owner_id.is_not(None), Deck.owner_id != user.id,
            Deck.unpublished_at.is_(None), Deck.share_token.is_not(None),
            func.lower(Deck.title).contains(term, autoescape=True)).order_by(*ranked_title(term))
        result['public_decks'] = page_of(db, statement, term, offset, size, lambda d, rows: deck_items(d, rows, 'public'))
    else:
        result['public_decks'] = empty
    if 'mine' in wanted:
        statement = select(Deck).where(Deck.owner_id == user.id,
                                       func.lower(Deck.title).contains(term, autoescape=True)).order_by(*ranked_title(term))
        result['my_decks'] = page_of(db, statement, term, offset, size, lambda d, rows: deck_items(d, rows, 'mine'))
    else:
        result['my_decks'] = empty
    if 'users' in wanted:
        statement = select(User).where(
            User.profile_visibility == 'public', User.suspended_at.is_(None), User.id != user.id,
            User.username.contains(term, autoescape=True) | func.lower(User.display_name).contains(term, autoescape=True),
        ).order_by(func.lower(User.username).startswith(term, autoescape=True).desc(), User.username)
        result['users'] = page_of(db, statement, term, offset, size, lambda _db, rows: [user_item(row) for row in rows])
    else:
        result['users'] = empty
    return result


@router.get('/recent')
def resolve_recent(ref: list[str] = Query([], max_length=64), user: User = Depends(require_user),
                   db: Session = Depends(get_db)):
    """Re-check the browser's remembered visits against current visibility before showing them.

    The browser stores only references (never titles), so a deck that became private or a profile that
    was hidden since the visit is dropped here instead of leaking its name from local storage.
    """
    items, seen = [], set()
    for value in ref[:MAX_RECENT]:
        if value in seen or not REF.match(value):
            continue
        seen.add(value)
        kind, _, key = value.partition(':')
        if kind == 'deck':
            deck = db.scalar(select(Deck).where(Deck.id == int(key), Deck.owner_id == user.id))
            found = deck_items(db, [deck], 'mine')[0] if deck else None
        elif kind == 'shared':
            deck = db.scalar(select(Deck).where(
                Deck.share_token == key, Deck.owner_id.is_not(None), Deck.unpublished_at.is_(None),
                Deck.visibility.in_(('public', 'unlisted'))))
            found = deck_items(db, [deck], 'public')[0] if deck else None
            if found and deck.visibility == 'unlisted':
                found['visibility'] = 'unlisted'
        else:
            profile = db.scalar(select(User).where(User.username == key, User.suspended_at.is_(None)))
            found = user_item(profile) if profile and (profile.id == user.id or profile.profile_visibility != 'private') else None
        if found:
            items.append(found)
    return {'items': items}
