"""Storage limits for new writes. Existing rows remain readable and removable."""
from fastapi import HTTPException
from sqlalchemy import func, select

from app.auth.service import reserve_account_action
from app.models import Deck, Flashcard, MultipleChoiceQuestion, MultipleChoiceSession, StudySession, StudySessionCard

MIB = 1024 * 1024
MAX_DECKS = 100
MAX_CARDS = 150
MAX_DECK_MEDIA = 12 * MIB
MAX_ACCOUNT_MEDIA = 64 * MIB
MAX_HISTORY_MEDIA = 192 * MIB
MAX_SESSIONS_PER_MODE = 500
MAX_DECK_COPIES_PER_WINDOW = 6
MAX_CLASSIC_STARTS_PER_WINDOW = 20


def require_operation_budget(db, user_id, action, limit):
    retry = reserve_account_action(db, f'{action}:{user_id}', limit)
    if retry:
        raise HTTPException(429, 'Too many requests for this action. Try again later.',
                            headers={'Retry-After': str(retry)})


def media_bytes(front, back):
    return len(front or '') + len(back or '')


def media_size(model):
    return func.coalesce(func.length(model.front_image), 0) + func.coalesce(func.length(model.back_image), 0)


def total_media(db, model, *filters):
    return db.scalar(select(func.coalesce(func.sum(media_size(model)), 0)).where(*filters))


def deck_media(db, deck_id):
    return total_media(db, Flashcard, Flashcard.deck_id == deck_id)


def require_deck_slot(db, user_id):
    if db.scalar(select(func.count()).select_from(Deck).where(Deck.owner_id == user_id)) >= MAX_DECKS:
        raise HTTPException(409, 'This account has reached its deck limit.')


def require_card_media(db, user_id, deck_id, extra):
    if extra <= 0:
        return
    if (extra > MAX_DECK_MEDIA or
            (deck_id is not None and deck_media(db, deck_id) + extra > MAX_DECK_MEDIA)):
        raise HTTPException(409, 'This deck has reached its photo storage limit.')
    account = select(func.coalesce(func.sum(media_size(Flashcard)), 0)).join(Deck).where(Deck.owner_id == user_id)
    if db.scalar(account) + extra > MAX_ACCOUNT_MEDIA:
        raise HTTPException(409, 'This account has reached its flashcard photo storage limit.')


def history_media_remaining(db, user_id):
    classic = select(func.coalesce(func.sum(media_size(StudySessionCard)), 0)).join(
        StudySession, StudySessionCard.session_id == StudySession.id).where(StudySession.owner_id == user_id)
    multiple = select(func.coalesce(func.sum(media_size(MultipleChoiceQuestion)), 0)).join(
        MultipleChoiceSession, MultipleChoiceQuestion.session_id == MultipleChoiceSession.id
    ).where(MultipleChoiceSession.owner_id == user_id)
    return max(0, MAX_HISTORY_MEDIA - db.scalar(classic) - db.scalar(multiple))


def history_media_available(db, user_id, extra):
    return not extra or extra <= history_media_remaining(db, user_id)


def require_study_slot(db, model, user_id, deck_id):
    if model is StudySession:
        require_operation_budget(db, user_id, 'classic-start', MAX_CLASSIC_STARTS_PER_WINDOW)
    count = select(func.count()).select_from(model).where(model.owner_id == user_id)
    if db.scalar(count) >= MAX_SESSIONS_PER_MODE:
        raise HTTPException(409, 'This account has reached its study history limit for this mode.')
    cards, amount = db.execute(select(func.count(), func.coalesce(func.sum(media_size(Flashcard)), 0))
                               .where(Flashcard.deck_id == deck_id)).one()
    if cards > MAX_CARDS:
        raise HTTPException(409, 'This deck contains too many cards to start a study session.')
    if amount > MAX_DECK_MEDIA:
        raise HTTPException(409, 'Reduce the photos in this deck before starting another study session.')
    if not history_media_available(db, user_id, amount):
        raise HTTPException(409, 'This account has reached its study photo storage limit.')
