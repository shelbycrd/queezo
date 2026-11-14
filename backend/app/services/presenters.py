from datetime import timezone

from sqlalchemy import func, select

from app.models import Flashcard, StudySessionCard, utcnow


def iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def deck_view(db, deck):
    count = db.scalar(select(func.count()).select_from(Flashcard).where(Flashcard.deck_id == deck.id))
    return {"id": deck.id, "title": deck.title, "card_count": count,
            "created_at": iso(deck.created_at), "updated_at": iso(deck.updated_at)}


def card_view(card):
    return {"id": card.id, "deck_id": card.deck_id, "card_type": card.card_type,
            "front": card.front, "back": card.back,
            "created_at": iso(card.created_at), "updated_at": iso(card.updated_at)}


def session_view(db, session):
    db.flush()
    completed = db.scalar(select(func.count()).select_from(StudySessionCard).where(
        StudySessionCard.session_id == session.id, StudySessionCard.completed.is_(True)))
    card = db.get(StudySessionCard, session.current_card_id) if session.current_card_id else None
    current = None
    if card and session.status == "active":
        current = {"id": card.id, "card_type": card.card_type, "front": card.front,
                   "review_count": card.review_count, "target_reviews": card.target_reviews}
        # Do not include the answer key at all before a two-sided reveal.
        if session.revealed:
            current["back"] = card.back
    return {"id": session.id, "deck_id": session.deck_id, "deck_title": session.deck_title,
            "status": session.status, "started_at": iso(session.started_at),
            "total_cards": session.total_cards, "completed_cards": completed,
            "total_reviews": session.total_reviews,
            "presentation_number": session.total_reviews + 1 if current else None,
            "presentation_token": session.presentation_token if current else None,
            "revealed": session.revealed if current else False, "current_card": current}


def summary_view(db, session):
    unique = db.scalar(select(func.count()).select_from(StudySessionCard).where(
        StudySessionCard.session_id == session.id, StudySessionCard.review_count > 0))
    end = session.completed_at or utcnow()
    return {"session_id": session.id, "deck_id": session.deck_id, "deck_title": session.deck_title,
            "status": session.status, "total_unique_cards": unique, "total_cards": session.total_cards,
            "total_reviews": session.total_reviews, "easy_count": session.easy_count,
            "normal_count": session.normal_count, "hard_count": session.hard_count,
            "started_at": iso(session.started_at), "completed_at": iso(session.completed_at),
            "duration_seconds": max(0, int((end - session.started_at).total_seconds()))}
