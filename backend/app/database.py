"""One connection per request; serialize writes before reading mutable state."""
import os
import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.sqlite_ops import pre_migration_snapshot


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    engine = create_engine(url, hide_parameters=True, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    return engine


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/queezo.db")
if DATABASE_URL.startswith("sqlite:///"):
    Path(DATABASE_URL.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
engine = make_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


SCHEMA_VERSION = 6
logger = logging.getLogger(__name__)


def enable_wal(connection):
    # Concurrent starters may briefly race while changing the journal mode.
    for attempt in range(5):
        try:
            mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
            if mode != "wal":
                mode = connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar()
            connection.commit()
            if mode not in {"wal", "memory"}:
                raise RuntimeError("SQLite did not enter WAL mode.")
            return
        except OperationalError as error:
            connection.rollback()
            if attempt == 4 or getattr(error.orig, "sqlite_errorcode", None) not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                raise
            time.sleep(0.2 * (attempt + 1))


def init_database(target=engine):
    from app import models  # Register models before creating tables.

    stage = "opening database"
    try:
        with target.connect() as connection:
            enable_wal(connection)
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            # The same writer guard serializes migrations across processes.
            version = connection.exec_driver_sql("PRAGMA user_version").scalar()
            if version == SCHEMA_VERSION:
                connection.commit()
                return
            if version not in {0, 1, 2, 3, 4, 5}:
                raise RuntimeError("Unsupported SQLite schema version. Use the matching Queezo release.")
            existing = connection.exec_driver_sql(
                "SELECT 1 FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
            ).first()
            if existing:
                stage = "verifying pre-migration backup"
                pre_migration_snapshot(connection.connection.driver_connection)
                logger.info("Verified SQLite pre-migration backup")
            stage = f"applying schema version {SCHEMA_VERSION}"
            Base.metadata.create_all(connection)
            if version == 0:
                upgrade_baseline(connection)
            if version < 3:
                upgrade_shared_distractors(connection)
            upgrade_admin_console(connection)
            upgrade_room_codes(connection)
            if version < 6:
                upgrade_achievements(connection)
            connection.exec_driver_sql(f"PRAGMA user_version={SCHEMA_VERSION}")
            connection.commit()
            logger.info("SQLite schema upgraded to version %s", SCHEMA_VERSION)
    except (OSError, sqlite3.Error, SQLAlchemyError, ValueError):
        raise RuntimeError(f"SQLite startup failed while {stage}. See the database recovery runbook.") from None


def upgrade_shared_distractors(connection):
    cache_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(flashcard_distractor_cache)")}
    if "source" not in cache_columns:
        connection.exec_driver_sql("""
            ALTER TABLE flashcard_distractor_cache ADD COLUMN source VARCHAR(8) NOT NULL DEFAULT 'ollama'
            CHECK (source IN ('ollama', 'fallback'))
        """)
        connection.exec_driver_sql("""
            UPDATE flashcard_distractor_cache SET source = 'fallback' WHERE EXISTS (
                SELECT 1 FROM flashcard_distractor_sources AS provenance
                WHERE provenance.flashcard_id = flashcard_distractor_cache.flashcard_id
            )
        """)
    session_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(multiple_choice_sessions)")}
    if "shared_access" not in session_columns:
        connection.exec_driver_sql("ALTER TABLE multiple_choice_sessions ADD COLUMN shared_access VARCHAR(64)")


def upgrade_admin_console(connection):
    for table, column, declaration in (
        ("users", "suspended_at", "DATETIME"),
        ("decks", "unpublished_at", "DATETIME"),
        ("profile_reports", "disposition", "VARCHAR(9) CHECK (disposition IN ('resolved', 'dismissed'))"),
    ):
        present = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")}
        if column not in present:
            connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def upgrade_room_codes(connection):
    """Add public room codes additively and backfill every existing room with a unique random code."""
    import secrets

    present = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(study_rooms)")}
    if "code" not in present:
        connection.exec_driver_sql("ALTER TABLE study_rooms ADD COLUMN code VARCHAR(8)")
    used = {row[0] for row in connection.exec_driver_sql("SELECT code FROM study_rooms WHERE code IS NOT NULL")}
    for (room_id,) in connection.exec_driver_sql("SELECT id FROM study_rooms WHERE code IS NULL").fetchall():
        code = secrets.token_hex(4).upper()
        while code in used:
            code = secrets.token_hex(4).upper()
        used.add(code)
        connection.exec_driver_sql("UPDATE study_rooms SET code = ? WHERE id = ?", (code, room_id))
    connection.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS ix_study_rooms_code ON study_rooms (code)")


def upgrade_achievements(connection):
    """V6: record each room session's starting host and backfill Studious from reliable history.

    Only completed Classic and Multiple-Choice sessions carry trustworthy completion times, so
    only Studious is backfilled. Deck Master cannot separate copied decks from original ones and
    misses deleted decks, and past room sessions never recorded their starting host, so those
    start at zero instead of guessing. Runs once (guarded by the schema version), before any
    request can emit events, so backfilled completions are never counted again.
    """
    from collections import defaultdict
    from datetime import date, datetime, timedelta, timezone

    present = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(study_room_sessions)")}
    if "host_id" not in present:
        connection.exec_driver_sql(
            "ALTER TABLE study_room_sessions ADD COLUMN host_id INTEGER REFERENCES users (id) ON DELETE SET NULL")
    manila = timezone(timedelta(hours=8))
    completions = defaultdict(list)
    for user_id, finished in connection.exec_driver_sql("""
        SELECT owner_id, completed_at FROM study_sessions
         WHERE status = 'completed' AND completed_at IS NOT NULL AND owner_id IN (SELECT id FROM users)
        UNION ALL
        SELECT owner_id, finished_at FROM multiple_choice_sessions
         WHERE status = 'completed' AND finished_at IS NOT NULL AND owner_id IN (SELECT id FROM users)
    """):
        moment = finished if isinstance(finished, datetime) else datetime.fromisoformat(str(finished))
        day = moment.replace(tzinfo=timezone.utc).astimezone(manila).date()
        completions[(user_id, day)].append(moment)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today = now.replace(tzinfo=timezone.utc).astimezone(manila).date()
    goal = 10
    best = {}
    for (user_id, day), moments in sorted(completions.items()):
        moments.sort()
        if len(moments) >= goal and (user_id not in best or best[user_id][0] != "unlocked"):
            best[user_id] = ("unlocked", day, goal, moments[goal - 1])
        elif day == today and user_id not in best:
            best[user_id] = ("progress", day, len(moments), None)
    for user_id, (_, day, progress, unlocked_at) in best.items():
        connection.exec_driver_sql(
            "INSERT OR IGNORE INTO user_achievements (user_id, achievement_key, progress, period_date, unlocked_at, updated_at)"
            " VALUES (?, 'studious', ?, ?, ?, ?)",
            (user_id, progress, date.isoformat(day), unlocked_at.isoformat(sep=' ') if unlocked_at else None,
             now.isoformat(sep=' ')))


def upgrade_baseline(connection):
    from app.migrate_cards import legacy_cards
    from app.ownership_migration import migrate_ownership
    from app.media_migration import migrate_card_images
    from app.profile_migration import migrate_profiles, migrate_profile_customization
    from app.sharing_migration import migrate_sharing

    migrate_ownership(connection)
    migrate_profiles(connection)
    migrate_card_images(connection)
    migrate_sharing(connection)
    migrate_profile_customization(connection)
    # Existing multiple-choice sessions default to unlimited timing.
    for table, fields in (
        ("multiple_choice_sessions", {
            "timing_scope": "VARCHAR(8)", "timing_seconds": "INTEGER", "deck_deadline": "DATETIME",
            "study_started_at": "DATETIME", "preparation_finished_at": "DATETIME",
        }),
        ("multiple_choice_questions", {
            "question_deadline": "DATETIME", "timed_out_at": "DATETIME",
            "allows_retry": "BOOLEAN", "eliminated_option_id": "VARCHAR(36)",
        }),
    ):
        columns = {row[1] for row in connection.execute(text(f"PRAGMA table_info({table})"))}
        for name, kind in fields.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {kind}"))
        if table == "multiple_choice_sessions" and "preparation_finished_at" not in columns:
            connection.execute(text("""
                UPDATE multiple_choice_sessions
                SET preparation_finished_at = COALESCE(finished_at, created_at),
                    study_started_at = CASE WHEN status IN ('active', 'completed') THEN created_at END
                WHERE status <> 'preparing'
            """))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_mc_questions_source_card ON multiple_choice_questions (source_card_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_login_throttles_window_started ON login_throttles (window_started)"))
    legacy = {table: [row["id"] for row in rows] for table, rows in legacy_cards(connection).items() if rows}
    if legacy:
        raise RuntimeError(
            f"Legacy cards need explicit back content before startup: {legacy}. "
            "Run python -m app.migrate_cards, then --answers answers.json; see README.md. "
            "No existing cards or history were deleted."
        )
    # create_all does not change old SQLite CHECK constraints. Add guards
    # on both new and existing databases without rebuilding/deleting tables.
    for table in ("flashcards", "study_session_cards"):
        for operation in ("INSERT", "UPDATE"):
            connection.execute(text(f"""
                CREATE TRIGGER IF NOT EXISTS {table}_two_sided_{operation.lower()}
                BEFORE {operation} ON {table}
                WHEN NEW.card_type IS NOT 'two_sided' OR NEW.back IS NULL
                     OR length(trim(NEW.back)) NOT BETWEEN 1 AND 10000
                BEGIN SELECT RAISE(ABORT, 'All cards require two sides'); END
            """))
    connection.execute(text("""
        CREATE TRIGGER IF NOT EXISTS flashcard_distractors_invalidate
        AFTER UPDATE OF front, back ON flashcards
        WHEN NEW.front IS NOT OLD.front OR NEW.back IS NOT OLD.back
        BEGIN
            DELETE FROM flashcard_distractor_cache WHERE flashcard_id = NEW.id;
        END
    """))
    connection.execute(text("""
        CREATE TRIGGER IF NOT EXISTS flashcard_limit
        BEFORE INSERT ON flashcards
        WHEN (SELECT COUNT(*) FROM flashcards WHERE deck_id = NEW.deck_id) >= 150
        BEGIN SELECT RAISE(ABORT, 'Deck limit is 150 flashcards'); END
    """))

    # Clear dependent cache rows before deleting a source and its provenance.
    for event_name, clause in (
        ("update", "AFTER UPDATE OF front, back, deck_id ON flashcards "
         "WHEN NEW.front IS NOT OLD.front OR NEW.back IS NOT OLD.back OR NEW.deck_id IS NOT OLD.deck_id"),
        ("delete", "BEFORE DELETE ON flashcards"),
    ):
        connection.execute(text(f"""
            CREATE TRIGGER IF NOT EXISTS flashcard_distractor_source_{event_name}
            {clause}
            BEGIN
                DELETE FROM flashcard_distractor_cache WHERE flashcard_id IN (
                    SELECT flashcard_id FROM flashcard_distractor_sources WHERE source_card_id = OLD.id
                );
            END
        """))


def get_db():
    with SessionLocal() as db:
        yield db


def get_db_factory():
    return SessionLocal


@contextmanager
def write_transaction(factory):
    with factory.begin() as db:
        # SQLite has no SELECT FOR UPDATE. Serialize read/modify/write operations.
        db.execute(text("BEGIN IMMEDIATE"))
        yield db


def get_write_db():
    with write_transaction(SessionLocal) as db:
        yield db
