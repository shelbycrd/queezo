"""Per-user achievements: a code catalog plus incremental, idempotent progress rows.

Gameplay code reports successful actions with ``record(db, user_id, event)`` inside the
write transaction that performed the action. Callers fire an event only on a state
transition (deck inserted, session status changed to completed, room session finished
successfully), so retries and refreshes that do not repeat the transition never count twice.
Distinct-subject achievements also insert a credit row, which ignores repeated subjects.

Adding an achievement: add an ``Achievement`` to ``CATALOG``, map the event(s) that advance
it in ``EVENTS``, call ``record`` where that action succeeds, and add a badge in the frontend
(``AchievementBadge.vue``). No schema change is needed; rows are created lazily.
"""
from dataclasses import dataclass
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from app.models import AchievementCredit, UserAchievement, utcnow
from app.services.activity import MANILA, today_manila
from app.services.presenters import iso


@dataclass(frozen=True)
class Achievement:
    key: str
    name: str
    description: str
    goal: int
    scope: str  # 'lifetime' or 'daily' (Asia/Manila calendar day)
    distinct: bool = False  # count each subject once (requires a subject on record)


CATALOG = {item.key: item for item in (
    Achievement('deck_master', 'Deck Master', 'Create 10 decks.', 10, 'lifetime'),
    Achievement('studious', 'Studious', 'Complete 10 study sessions in one day.', 10, 'daily'),
    Achievement('hoster', 'Hoster', 'Host 6 different study rooms through a completed session.', 6, 'lifetime',
                distinct=True),
)}

EVENTS = {
    'deck_created': ('deck_master',),
    'study_completed': ('studious',),
    'room_hosted': ('hoster',),
}


def manila_day(moment):
    return moment.replace(tzinfo=timezone.utc).astimezone(MANILA).date()


def record(db, user_id, event, *, at=None, subject=None):
    """Advance every achievement tied to ``event``. Must run inside a write transaction."""
    if user_id is None:
        return
    moment = at or utcnow()
    for key in EVENTS[event]:
        _advance(db, user_id, CATALOG[key], moment, subject)


def _advance(db, user_id, achievement, moment, subject):
    row = db.get(UserAchievement, (user_id, achievement.key))
    if row is not None and row.unlocked_at is not None:
        return  # Permanent: progress stops once unlocked.
    if row is None:
        row = UserAchievement(user_id=user_id, achievement_key=achievement.key, progress=0)
        db.add(row)
    if achievement.scope == 'daily':
        day = manila_day(moment)
        if row.period_date is not None and row.period_date > day:
            return  # A late-processed completion from an earlier day cannot reopen that day.
        if row.period_date != day:
            row.period_date, row.progress = day, 0  # Lazy daily reset.
    if achievement.distinct:
        if subject is None:
            raise ValueError(f'{achievement.key} needs a subject to count distinct actions.')
        credited = db.execute(insert(AchievementCredit).values(
            user_id=user_id, achievement_key=achievement.key, subject=str(subject),
        ).on_conflict_do_nothing()).rowcount
        if not credited:
            return
    now = utcnow()
    row.progress += 1
    row.updated_at = now
    if row.progress >= achievement.goal:
        row.unlocked_at = now


def achievements_view(db, user_id, owner):
    """Owners see every achievement with progress; visitors see only names of unlocked ones."""
    rows = {row.achievement_key: row for row in db.scalars(
        select(UserAchievement).where(UserAchievement.user_id == user_id))}
    today = today_manila()
    items = []
    for achievement in CATALOG.values():
        row = rows.get(achievement.key)
        unlocked = row is not None and row.unlocked_at is not None
        if not owner and not unlocked:
            continue
        item = {'key': achievement.key, 'name': achievement.name, 'description': achievement.description,
                'unlocked': unlocked}
        if owner:
            progress = row.progress if row else 0
            if achievement.scope == 'daily' and not unlocked and (row is None or row.period_date != today):
                progress = 0
            item.update({'goal': achievement.goal, 'scope': achievement.scope,
                         'progress': min(progress, achievement.goal),
                         'unlocked_at': iso(row.unlocked_at) if unlocked else None})
        items.append(item)
    return items
