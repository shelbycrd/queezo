import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import init_database, make_engine
from app.migrate_cards import CARD_TABLES, legacy_cards, repair_cards


@pytest.fixture
def legacy_engine(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    with engine.begin() as connection:
        # Legacy permissive tables simulate a previously saved database.
        for table in CARD_TABLES:
            connection.execute(text(f"""CREATE TABLE {table} (
                id INTEGER PRIMARY KEY, card_type TEXT, front TEXT, back TEXT, deck_id INTEGER DEFAULT 1
            )"""))
            connection.execute(text(f"INSERT INTO {table} (id, card_type, front, back) VALUES (1, 'one_sided', 'Original prompt', NULL)"))
    yield engine
    engine.dispose()


def test_startup_requires_answers_without_deleting_legacy_data(legacy_engine):
    with pytest.raises(RuntimeError, match='Legacy cards need explicit back content'):
        init_database(legacy_engine)
    with legacy_engine.connect() as connection:
        for rows in legacy_cards(connection).values():
            assert [row['id'] for row in rows] == [1]
            assert rows[0]['front'] == 'Original prompt'


def test_explicit_atomic_conversion_and_idempotent_database_guards(legacy_engine):
    answers = {table: {'1': 'Supplied answer'} for table in CARD_TABLES}
    assert repair_cards(legacy_engine, answers) == 2
    init_database(legacy_engine)
    init_database(legacy_engine)
    with legacy_engine.connect() as connection:
        assert legacy_cards(connection) == {table: [] for table in CARD_TABLES}
        for table in CARD_TABLES:
            saved = connection.execute(text(f'SELECT * FROM {table} WHERE id = 1')).mappings().one()
            assert saved['front'] == 'Original prompt'
            assert saved['back'] == 'Supplied answer'
            assert saved['card_type'] == 'two_sided'
    for table in CARD_TABLES:
        with pytest.raises(IntegrityError), legacy_engine.begin() as connection:
            connection.execute(text(f"UPDATE {table} SET card_type = 'one_sided', back = NULL WHERE id = 1"))
        with pytest.raises(IntegrityError), legacy_engine.begin() as connection:
            connection.execute(text(f"INSERT INTO {table} (id, card_type, front, back) VALUES (2, 'two_sided', 'Question', '   ')"))


@pytest.mark.parametrize('answers', [
    {}, {'flashcards': {'1': 'Answer'}},
    {'flashcards': {'1': 'Answer'}, 'study_session_cards': {'1': '   '}},
    {'flashcards': {'1': 'Answer'}, 'study_session_cards': {'999': 'Answer'}},
    {'unknown': {}}, [],
])
def test_incomplete_or_invalid_conversion_rolls_back(legacy_engine, answers):
    with pytest.raises(ValueError):
        repair_cards(legacy_engine, answers)
    with legacy_engine.connect() as connection:
        assert all(len(rows) == 1 for rows in legacy_cards(connection).values())


def test_new_database_rejects_non_two_sided_cards(client):
    deck_id = client.post('/api/decks', json={'title': 'Test'}).json()['id']
    with pytest.raises(IntegrityError, match='All cards require two sides'), client.factory() as db:
        db.execute(text("""INSERT INTO flashcards (deck_id, card_type, front, back, created_at, updated_at)
                        VALUES (:deck_id, 'one_sided', 'Q', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""),
                   {'deck_id': deck_id})
