"""One connection per request; serialize writes before reading mutable state."""
import os
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

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


def init_database(target=engine):
    from app import models  # Register models before creating tables.
    from app.migrate_cards import legacy_cards
    from app.ownership_migration import migrate_ownership
    from app.media_migration import migrate_card_images

    Base.metadata.create_all(target)
    with target.begin() as connection:
        connection.execute(text("PRAGMA journal_mode=WAL")).scalar()
        migrate_ownership(connection)
        migrate_card_images(connection)
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
            CREATE TRIGGER IF NOT EXISTS flashcard_limit
            BEFORE INSERT ON flashcards
            WHEN (SELECT COUNT(*) FROM flashcards WHERE deck_id = NEW.deck_id) >= 150
            BEGIN SELECT RAISE(ABORT, 'Deck limit is 150 flashcards'); END
        """))


def get_db():
    with SessionLocal() as db:
        yield db


def get_write_db():
    with SessionLocal() as db:
        try:
            # SQLite has no SELECT FOR UPDATE. Acquire the write lock FIRST so
            # simultaneous requests cannot both consume a presentation or slot.
            db.execute(text("BEGIN IMMEDIATE"))
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
