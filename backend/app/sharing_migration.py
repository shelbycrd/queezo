"""Add visibility without publishing or replacing existing decks."""
import secrets
from sqlalchemy import inspect, text


def migrate_sharing(connection):
    columns = {column['name'] for column in inspect(connection).get_columns('decks')}
    if 'visibility' not in columns:
        connection.execute(text("ALTER TABLE decks ADD COLUMN visibility TEXT NOT NULL DEFAULT 'private'"))
    if 'share_token' not in columns:
        connection.execute(text('ALTER TABLE decks ADD COLUMN share_token TEXT'))
    for row in connection.execute(text('SELECT id FROM decks WHERE share_token IS NULL')).all():
        connection.execute(text('UPDATE decks SET share_token=:token WHERE id=:id'), {'id':row.id,'token':secrets.token_urlsafe(32)})
    connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ux_decks_share_token ON decks(share_token)'))
    for operation in ('INSERT','UPDATE'):
        connection.execute(text(f"""CREATE TRIGGER IF NOT EXISTS decks_visibility_{operation.lower()}
        BEFORE {operation} ON decks WHEN NEW.visibility IS NULL OR NEW.visibility NOT IN ('private','public','unlisted')
        BEGIN SELECT RAISE(ABORT, 'Invalid deck visibility'); END"""))
