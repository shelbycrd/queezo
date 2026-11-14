"""Add ownership without assigning or deleting pre-account academic records."""
from sqlalchemy import inspect, text


def migrate_ownership(connection):
    """Idempotent, additive SQLite migration; legacy owner IDs remain NULL."""
    for table in ("decks", "study_sessions"):
        inspector = inspect(connection)
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "owner_id" not in columns:
            connection.execute(text(
                f"ALTER TABLE {table} ADD COLUMN owner_id INTEGER REFERENCES users(id)"
            ))
        connection.execute(text(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_owner_id ON {table} (owner_id)"
        ))


def list_unowned(db):
    """CLI-only inventory. Legacy data is never exposed through account APIs."""
    return [dict(row) for row in db.execute(text("""
        SELECT d.id, d.title,
               (SELECT COUNT(*) FROM flashcards f WHERE f.deck_id = d.id) AS card_count,
               (SELECT COUNT(*) FROM study_sessions s WHERE s.deck_id = d.id) AS session_count
        FROM decks d WHERE d.owner_id IS NULL ORDER BY d.id
    """)).mappings()]


def assign_legacy(db, email, deck_ids):
    """Assign only explicitly selected unowned decks; caller owns transaction.

    Every requested deck is validated before updating anything. Associated
    snapshots and reviews stay in place and inherit access through the deck's
    study sessions. An owned deck cannot be reassigned with this command.
    """
    from app.auth.service import normalize_email

    normalized = normalize_email(email)
    if not deck_ids or any(type(identity) is not int or identity < 1 for identity in deck_ids):
        raise ValueError("Specify at least one positive --deck-id.")
    if len(set(deck_ids)) != len(deck_ids):
        raise ValueError("Specify each --deck-id only once.")
    user_id = db.execute(text("SELECT id FROM users WHERE email = :email"),
                         {"email": normalized}).scalar_one_or_none()
    if user_id is None:
        raise ValueError("That account does not exist. Create it before assigning legacy data.")

    for identity in deck_ids:
        deck = db.execute(text("SELECT id, owner_id FROM decks WHERE id = :id"),
                          {"id": identity}).mappings().one_or_none()
        if deck is None:
            raise ValueError(f"Deck {identity} does not exist.")
        if deck["owner_id"] is not None:
            raise ValueError(f"Deck {identity} already belongs to an account and cannot be reassigned.")
        conflicting = db.execute(text("""
            SELECT COUNT(*) FROM study_sessions
            WHERE deck_id = :id AND owner_id IS NOT NULL AND owner_id != :owner
        """), {"id": identity, "owner": user_id}).scalar_one()
        if conflicting:
            raise ValueError(f"Deck {identity} has study sessions owned by a different account. No data was changed.")

    session_count = 0
    for identity in deck_ids:
        db.execute(text("UPDATE decks SET owner_id = :owner WHERE id = :id AND owner_id IS NULL"),
                   {"id": identity, "owner": user_id})
        result = db.execute(text("""
            UPDATE study_sessions SET owner_id = :owner
            WHERE deck_id = :id AND owner_id IS NULL
        """), {"id": identity, "owner": user_id})
        session_count += result.rowcount
    return {"email": normalized, "deck_count": len(deck_ids), "session_count": session_count}
