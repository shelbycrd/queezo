"""Add optional photo columns without touching old questions or study history."""
from sqlalchemy import inspect, text


def migrate_card_images(connection):
    for table in ('flashcards', 'study_session_cards'):
        inspector = inspect(connection)
        if not inspector.has_table(table):
            continue
        columns = {column['name'] for column in inspector.get_columns(table)}
        for column in ('front_image', 'back_image'):
            if column not in columns:
                connection.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} TEXT'))
