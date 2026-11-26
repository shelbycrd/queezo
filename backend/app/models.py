from datetime import date, datetime, timezone
from uuid import uuid4
import secrets

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow():
    # SQLite stores naive UTC; serializers explicitly attach UTC on output.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Deck(Base):
    __tablename__ = "decks"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(120))
    visibility: Mapped[str] = mapped_column(String(8), default='private', server_default='private')
    unpublished_at: Mapped[datetime | None] = mapped_column(DateTime)
    share_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, default=lambda: secrets.token_urlsafe(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    __table_args__ = (CheckConstraint("length(trim(title)) BETWEEN 1 AND 120"), {"sqlite_autoincrement": True})


class Flashcard(Base):
    __tablename__ = "flashcards"
    id: Mapped[int] = mapped_column(primary_key=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id", ondelete="CASCADE"), index=True)
    card_type: Mapped[str] = mapped_column(String(16), default="two_sided")
    front: Mapped[str] = mapped_column(Text)
    back: Mapped[str] = mapped_column(Text)
    front_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    back_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        CheckConstraint("length(trim(front)) BETWEEN 1 AND 10000"),
        CheckConstraint("card_type = 'two_sided'"),
        CheckConstraint("length(trim(back)) BETWEEN 1 AND 10000"),
        {"sqlite_autoincrement": True},
    )


class FlashcardDistractorCache(Base):
    __tablename__ = "flashcard_distractor_cache"

    flashcard_id: Mapped[int] = mapped_column(ForeignKey("flashcards.id", ondelete="CASCADE"), primary_key=True)
    distractors: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    ollama_model: Mapped[str] = mapped_column(Text)
    generation_version: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(8), default="ollama", server_default="ollama")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        CheckConstraint("json_valid(distractors) AND json_type(distractors) = 'array' "
                        "AND json_array_length(distractors) = 3"),
        CheckConstraint("source IN ('ollama', 'fallback')"),
    )


class FlashcardDistractorSource(Base):
    """Provenance for one deck-derived choice. Slots without a row came from Ollama."""

    __tablename__ = "flashcard_distractor_sources"

    flashcard_id: Mapped[int] = mapped_column(
        ForeignKey("flashcard_distractor_cache.flashcard_id", ondelete="CASCADE"), primary_key=True,
    )
    position: Mapped[int] = mapped_column(primary_key=True)
    source_card_id: Mapped[int] = mapped_column(ForeignKey("flashcards.id", ondelete="CASCADE"), index=True)
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    __table_args__ = (CheckConstraint("position BETWEEN 0 AND 2 AND flashcard_id <> source_card_id"),)


class FlashcardDistractorJob(Base):
    """An expiring, fenced generation claim shared by all SQLite writers."""

    __tablename__ = "flashcard_distractor_jobs"

    flashcard_id: Mapped[int] = mapped_column(ForeignKey("flashcards.id", ondelete="CASCADE"), primary_key=True)
    token: Mapped[str] = mapped_column(String(36))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class MultipleChoiceSession(Base):
    __tablename__ = "multiple_choice_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id", ondelete="CASCADE"), index=True)
    deck_title: Mapped[str] = mapped_column(String(120))
    shared_access: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="preparing")
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    prepare_until: Mapped[datetime] = mapped_column(DateTime)
    timing_scope: Mapped[str | None] = mapped_column(String(8))
    timing_seconds: Mapped[int | None] = mapped_column(Integer)
    deck_deadline: Mapped[datetime | None] = mapped_column(DateTime)
    study_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    preparation_finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        CheckConstraint("status IN ('preparing', 'failed', 'active', 'completed', 'cancelled')"),
    )


class MultipleChoiceQuestion(Base):
    __tablename__ = "multiple_choice_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("multiple_choice_sessions.id", ondelete="CASCADE"))
    # Keep the source ID for failure reports and snapshots even after card deletion.
    source_card_id: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    front: Mapped[str | None] = mapped_column(Text)
    front_image: Mapped[str | None] = mapped_column(Text)
    back_image: Mapped[str | None] = mapped_column(Text)
    options: Mapped[list[dict[str, str]] | None] = mapped_column(JSON(none_as_null=True))
    correct_option_id: Mapped[str | None] = mapped_column(String(36))
    allows_retry: Mapped[bool | None] = mapped_column(Boolean)
    eliminated_option_id: Mapped[str | None] = mapped_column(String(36))
    selected_option_id: Mapped[str | None] = mapped_column(String(36))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime)
    failure: Mapped[str | None] = mapped_column(String(32))
    question_deadline: Mapped[datetime | None] = mapped_column(DateTime)
    timed_out_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("session_id", "position"),
        UniqueConstraint("session_id", "source_card_id"),
        CheckConstraint("(options IS NULL) = (correct_option_id IS NULL)"),
        CheckConstraint("failure IS NULL OR options IS NULL"),
        CheckConstraint("(selected_option_id IS NULL) = (answered_at IS NULL)"),
    )


class StudySession(Base):
    __tablename__ = "study_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id", ondelete="CASCADE"), index=True)
    deck_title: Mapped[str] = mapped_column(String(120))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    total_cards: Mapped[int] = mapped_column(Integer)
    total_reviews: Mapped[int] = mapped_column(Integer, default=0)
    easy_count: Mapped[int] = mapped_column(Integer, default=0)
    normal_count: Mapped[int] = mapped_column(Integer, default=0)
    hard_count: Mapped[int] = mapped_column(Integer, default=0)
    random_seed: Mapped[str] = mapped_column(String(36))
    virtual_position: Mapped[int] = mapped_column(Integer, default=0)
    current_card_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    presentation_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    revealed: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (CheckConstraint("status IN ('active', 'completed', 'exited')"),)


class StudySessionCard(Base):
    __tablename__ = "study_session_cards"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("study_sessions.id", ondelete="CASCADE"), index=True)
    flashcard_id: Mapped[int | None] = mapped_column(ForeignKey("flashcards.id", ondelete="SET NULL"), nullable=True, index=True)
    # Snapshots keep active sessions and history stable when a card is edited/deleted.
    card_type: Mapped[str] = mapped_column(String(16), default="two_sided")
    front: Mapped[str] = mapped_column(Text)
    back: Mapped[str] = mapped_column(Text)
    front_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    back_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    initial_order: Mapped[int] = mapped_column(Integer)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    latest_difficulty: Mapped[str | None] = mapped_column(String(8), nullable=True)
    target_reviews: Mapped[int] = mapped_column(Integer, default=2)
    next_eligible_position: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        UniqueConstraint("session_id", "initial_order"),
        CheckConstraint("card_type = 'two_sided'"),
        CheckConstraint("length(trim(back)) BETWEEN 1 AND 10000"),
        CheckConstraint("review_count BETWEEN 0 AND 4"),
        CheckConstraint("target_reviews BETWEEN 2 AND 4"),
    )


class StudyReview(Base):
    __tablename__ = "study_reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("study_sessions.id", ondelete="CASCADE"), index=True)
    session_card_id: Mapped[int] = mapped_column(ForeignKey("study_session_cards.id", ondelete="CASCADE"), index=True)
    difficulty: Mapped[str] = mapped_column(String(8))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    presentation_number: Mapped[int] = mapped_column(Integer)
    presentation_token: Mapped[str] = mapped_column(String(36))
    __table_args__ = (
        UniqueConstraint("session_id", "presentation_number"),
        UniqueConstraint("session_id", "presentation_token"),
        CheckConstraint("difficulty IN ('easy', 'normal', 'hard')"),
    )


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()))
    username: Mapped[str] = mapped_column(String(32, collation="NOCASE"), unique=True, default=lambda: 'user_' + uuid4().hex[:20])
    display_name: Mapped[str] = mapped_column(String(80), default='Learner')
    email: Mapped[str] = mapped_column(String(254, collation="NOCASE"), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    profile_visibility: Mapped[str] = mapped_column(String(8), default='unlisted', server_default='unlisted')
    bio: Mapped[str] = mapped_column(String(200), default='', server_default='')
    interest_tags: Mapped[list[str]] = mapped_column(JSON, default=list, server_default='[]')
    avatar: Mapped[str] = mapped_column(String(8), default='cat', server_default='cat')
    display_name_changed_at: Mapped[datetime | None] = mapped_column(DateTime)
    featured_deck_id: Mapped[int | None] = mapped_column(ForeignKey("decks.id", ondelete="SET NULL", use_alter=True))
    __table_args__ = ({"sqlite_autoincrement": True},)


class ProfileAvatarChange(Base):
    __tablename__ = "profile_avatar_changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    changed_at: Mapped[datetime] = mapped_column(DateTime)
    __table_args__ = (Index("ix_profile_avatar_user_time", "user_id", "changed_at"),)


class ProfileReport(Base):
    __tablename__ = "profile_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(24))
    explanation: Mapped[str] = mapped_column(String(400), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    disposition: Mapped[str | None] = mapped_column(String(9))
    __table_args__ = (CheckConstraint("target_id <> reporter_id"),
                      CheckConstraint("disposition IN ('resolved', 'dismissed')"),
                      {"sqlite_autoincrement": True})


class AdminCredential(Base):
    __tablename__ = "admin_credential"
    id: Mapped[int] = mapped_column(primary_key=True)
    operator: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(512))
    revision: Mapped[int] = mapped_column(Integer)
    __table_args__ = (CheckConstraint("id = 1"),)


class AdminAudit(Base):
    __tablename__ = "admin_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    operator: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(40))
    target: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(String(240))
    outcome: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = ({"sqlite_autoincrement": True},)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class LoginThrottle(Base):
    __tablename__ = "login_throttles"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    window_started: Mapped[datetime] = mapped_column(DateTime, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class ActivityDay(Base):
    __tablename__ = "activity_days"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)


class Friendship(Base):
    __tablename__ = "friendships"
    first_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    second_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    requester_id: Mapped[int] = mapped_column(Integer)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        CheckConstraint("first_id < second_id"),
        CheckConstraint("requester_id IN (first_id, second_id)"),
    )


class SessionPresence(Base):
    __tablename__ = "session_presence"
    session_hash: Mapped[str] = mapped_column(
        ForeignKey("auth_sessions.token_hash", ondelete="CASCADE"), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime)


class StudyRoom(Base):
    __tablename__ = "study_rooms"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    host_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    deck_id: Mapped[int | None] = mapped_column(ForeignKey("decks.id", ondelete="SET NULL"))
    deck_owner_id: Mapped[int | None] = mapped_column(Integer)
    share_private: Mapped[bool] = mapped_column(Boolean, default=False)
    mode: Mapped[str] = mapped_column(String(16), default="collaborative")
    seconds: Mapped[int] = mapped_column(Integer, default=30)
    phase: Mapped[str] = mapped_column(String(16), default="lobby", index=True)
    session_id: Mapped[str | None] = mapped_column(String(36))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class RoomMember(Base):
    __tablename__ = "study_room_members"
    room_id: Mapped[str] = mapped_column(ForeignKey("study_rooms.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime)
    ready: Mapped[bool] = mapped_column(Boolean, default=False)
    spectator: Mapped[bool] = mapped_column(Boolean, default=False)


class RoomInvite(Base):
    __tablename__ = "study_room_invites"
    room_id: Mapped[str] = mapped_column(ForeignKey("study_rooms.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RoomSession(Base):
    __tablename__ = "study_room_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("study_rooms.id", ondelete="CASCADE"), index=True)
    deck_title: Mapped[str] = mapped_column(String(120))
    mode: Mapped[str] = mapped_column(String(16))
    players: Mapped[dict] = mapped_column(JSON)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    position: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    claim: Mapped[str | None] = mapped_column(String(36))
    claim_until: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class RoomQuestion(Base):
    __tablename__ = "study_room_questions"
    session_id: Mapped[str] = mapped_column(ForeignKey("study_room_sessions.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int | None] = mapped_column(ForeignKey("flashcards.id", ondelete="SET NULL"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    front: Mapped[str | None] = mapped_column(Text)
    front_image: Mapped[str | None] = mapped_column(Text)
    back_image: Mapped[str | None] = mapped_column(Text)
    options: Mapped[list | None] = mapped_column(JSON(none_as_null=True))
    correct_id: Mapped[str | None] = mapped_column(String(36))
    failed: Mapped[bool] = mapped_column(Boolean, default=False)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)


class RoomMessage(Base):
    __tablename__ = "study_room_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("study_rooms.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    author: Mapped[dict] = mapped_column(JSON)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = ({"sqlite_autoincrement": True},)
