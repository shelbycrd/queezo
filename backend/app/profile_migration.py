"""Add account identities without replacing users or changing their ownership."""
from uuid import uuid4
from sqlalchemy import inspect, text


def migrate_profiles(connection):
    columns = {item['name'] for item in inspect(connection).get_columns('users')}
    for name in ('uid', 'username', 'display_name'):
        if name not in columns:
            connection.execute(text(f'ALTER TABLE users ADD COLUMN {name} TEXT'))
    for row in connection.execute(text('SELECT id,email,uid,username,display_name FROM users')).mappings().all():
        uid = row['uid'] or str(uuid4())
        username = row['username'] or f"user_{row['id']}"
        if not row['username']:
            while connection.execute(text('SELECT id FROM users WHERE username = :name COLLATE NOCASE AND id != :id'), {'name':username,'id':row['id']}).first():
                username = f"user_{row['id']}_{uuid4().hex[:8]}"
        name = row['display_name'] or row['email'].split('@')[0][:80] or 'Learner'
        connection.execute(text('UPDATE users SET uid=:uid,username=:username,display_name=:name WHERE id=:id'), {'uid':uid,'username':username,'name':name,'id':row['id']})
    connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ux_users_uid ON users(uid)'))
    connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username ON users(username COLLATE NOCASE)'))
    for operation in ('INSERT', 'UPDATE'):
        connection.execute(text(f"""CREATE TRIGGER IF NOT EXISTS users_identity_{operation.lower()}
          BEFORE {operation} ON users WHEN NEW.uid IS NULL OR length(NEW.uid) != 36
          OR NEW.username IS NULL OR length(NEW.username) NOT BETWEEN 3 AND 32
          OR NEW.display_name IS NULL OR length(trim(NEW.display_name)) NOT BETWEEN 1 AND 80
          BEGIN SELECT RAISE(ABORT, 'Account identity is required'); END"""))


def migrate_profile_customization(connection):
    columns = {item['name'] for item in inspect(connection).get_columns('users')}
    fields = {
        'profile_visibility': "VARCHAR(8) NOT NULL DEFAULT 'unlisted'",
        'bio': "VARCHAR(200) NOT NULL DEFAULT ''",
        'interest_tags': "JSON NOT NULL DEFAULT '[]'",
        'avatar': "VARCHAR(8) NOT NULL DEFAULT 'cat'",
        'display_name_changed_at': 'DATETIME',
        'featured_deck_id': 'INTEGER REFERENCES decks(id) ON DELETE SET NULL',
    }
    for name, definition in fields.items():
        if name not in columns:
            connection.execute(text(f'ALTER TABLE users ADD COLUMN {name} {definition}'))
    connection.execute(text("""
        CREATE TRIGGER IF NOT EXISTS users_immutable_username
        BEFORE UPDATE OF username ON users WHEN NEW.username COLLATE BINARY IS NOT OLD.username COLLATE BINARY
        BEGIN SELECT RAISE(ABORT, 'Username cannot be changed'); END
    """))
    connection.execute(text("""
        CREATE TRIGGER IF NOT EXISTS clear_inaccessible_featured_deck
        AFTER UPDATE OF visibility, owner_id, share_token ON decks
        BEGIN
            UPDATE users SET featured_deck_id = NULL
            WHERE featured_deck_id = NEW.id AND
                (id IS NOT NEW.owner_id OR NEW.visibility <> 'public' OR NEW.share_token IS NULL);
        END
    """))
