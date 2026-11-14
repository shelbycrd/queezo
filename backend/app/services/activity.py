"""Account-private study days; calendar boundaries follow Asia/Manila (UTC+8)."""
from datetime import date, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert

from app.models import ActivityDay, Deck, StudyReview, StudySession, utcnow

MANILA = timezone(timedelta(hours=8))


def today_manila():
    return utcnow().replace(tzinfo=timezone.utc).astimezone(MANILA).date()


def mark_study_day(db, user_id):
    db.execute(insert(ActivityDay).values(user_id=user_id, day=today_manila()).on_conflict_do_nothing(
        index_elements=['user_id', 'day']))


def activity_view(db, user):
    today = today_manila()
    days = set(db.scalars(select(ActivityDay.day).where(ActivityDay.user_id == user.id, ActivityDay.day <= today)))
    # Older sessions predate activity_days. Derive their actual review days,
    # restricted through both session and deck ownership, without reassigning data.
    review_days = db.scalars(select(func.date(StudyReview.reviewed_at, '+8 hours')).join(
        StudySession, StudyReview.session_id == StudySession.id).join(Deck, StudySession.deck_id == Deck.id).where(
            StudySession.owner_id == user.id, Deck.owner_id == user.id).distinct())
    for value in review_days:
        if value:
            parsed = date.fromisoformat(value)
            if parsed <= today:
                days.add(parsed)
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return {'study_streak':streak, 'active_today':today in days,
            'active_days':[value.isoformat() for value in sorted(days)],
            'today':today.isoformat(), 'timezone':'Asia/Manila'}
