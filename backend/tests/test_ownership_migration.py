import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.database import make_engine
from app.ownership_migration import assign_legacy, list_unowned, migrate_ownership


@pytest.fixture
def ownership_engine(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'ownership.db').as_posix()}")
    with engine.begin() as db:
        db.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE)"))
        db.execute(text("CREATE TABLE decks (id INTEGER PRIMARY KEY, title TEXT NOT NULL)"))
        db.execute(text("CREATE TABLE study_sessions (id TEXT PRIMARY KEY, deck_id INTEGER REFERENCES decks(id), label TEXT)"))
        db.execute(text("CREATE TABLE flashcards (id INTEGER PRIMARY KEY, deck_id INTEGER REFERENCES decks(id), front TEXT, back TEXT)"))
        db.execute(text("CREATE TABLE study_session_cards (id INTEGER PRIMARY KEY, session_id TEXT REFERENCES study_sessions(id), front TEXT, back TEXT)"))
        db.execute(text("CREATE TABLE study_reviews (id INTEGER PRIMARY KEY, session_card_id INTEGER REFERENCES study_session_cards(id), difficulty TEXT)"))
        db.execute(text("INSERT INTO users VALUES (1, 'alice@example.com'), (2, 'bob@example.com')"))
        db.execute(text("INSERT INTO decks VALUES (10, 'Legacy A'), (20, 'Legacy B'), (30, 'Owned')"))
        db.execute(text("INSERT INTO study_sessions VALUES ('old-session', 10, 'Preserved history')"))
        db.execute(text("INSERT INTO flashcards VALUES (100, 10, 'Original Q', 'Original A')"))
        db.execute(text("INSERT INTO study_session_cards VALUES (200, 'old-session', 'Historical Q', 'Historical A')"))
        db.execute(text("INSERT INTO study_reviews VALUES (300, 200, 'easy')"))
        migrate_ownership(db)
        db.execute(text("UPDATE decks SET owner_id = 2 WHERE id = 30"))
    yield engine
    engine.dispose()


def academic_content(db):
    return {
        'decks': db.execute(text('SELECT id, title FROM decks ORDER BY id')).all(),
        'sessions': db.execute(text('SELECT id, deck_id, label FROM study_sessions')).all(),
        'cards': db.execute(text('SELECT * FROM flashcards')).all(),
        'snapshots': db.execute(text('SELECT * FROM study_session_cards')).all(),
        'reviews': db.execute(text('SELECT * FROM study_reviews')).all(),
    }


def test_additive_migration_is_repeatable_and_does_not_assign_existing_records(ownership_engine):
    with ownership_engine.begin() as db:
        before = academic_content(db)
        migrate_ownership(db)
        migrate_ownership(db)
        assert academic_content(db) == before
        for table in ['decks', 'study_sessions']:
            columns = inspect(db).get_columns(table)
            assert sum(column['name'] == 'owner_id' for column in columns) == 1
            assert next(column for column in columns if column['name'] == 'owner_id')['nullable']
            assert any(index['column_names'] == ['owner_id'] for index in inspect(db).get_indexes(table))
            assert any(foreign['constrained_columns'] == ['owner_id'] and foreign['referred_table'] == 'users'
                       for foreign in inspect(db).get_foreign_keys(table))
        assert db.execute(text('SELECT owner_id FROM decks WHERE id = 10')).scalar_one() is None
        assert db.execute(text('SELECT owner_id FROM study_sessions')).scalar_one() is None


def test_inventory_and_explicit_assignment_preserve_contents_and_unselected_decks(ownership_engine):
    with Session(ownership_engine) as db:
        before = academic_content(db)
        assert list_unowned(db) == [
            {'id': 10, 'title': 'Legacy A', 'card_count': 1, 'session_count': 1},
            {'id': 20, 'title': 'Legacy B', 'card_count': 0, 'session_count': 0},
        ]
        result = assign_legacy(db, '  ALICE@EXAMPLE.COM ', [10])
        db.commit()
        assert result == {'email': 'alice@example.com', 'deck_count': 1, 'session_count': 1}
        assert academic_content(db) == before
        assert db.execute(text('SELECT owner_id FROM decks WHERE id = 10')).scalar_one() == 1
        assert db.execute(text('SELECT owner_id FROM study_sessions')).scalar_one() == 1
        assert db.execute(text('SELECT owner_id FROM decks WHERE id = 20')).scalar_one() is None
        assert db.execute(text('SELECT owner_id FROM decks WHERE id = 30')).scalar_one() == 2


@pytest.mark.parametrize('email,deck_ids', [
    ('alice@example.com', []), ('alice@example.com', [0]), ('alice@example.com', [-1]),
    ('alice@example.com', [True]), ('alice@example.com', [10, 10]),
    ('alice@example.com', [10, 99]), ('alice@example.com', [10, 30]),
    ('missing@example.com', [10]),
])
def test_invalid_selection_never_partially_assigns_records(ownership_engine, email, deck_ids):
    with Session(ownership_engine) as db:
        before = academic_content(db)
        with pytest.raises(ValueError):
            assign_legacy(db, email, deck_ids)
        db.commit()
        assert academic_content(db) == before
        assert db.execute(text('SELECT owner_id FROM decks WHERE id = 10')).scalar_one() is None
        assert db.execute(text('SELECT owner_id FROM study_sessions')).scalar_one() is None


def test_conflicting_study_owner_rejects_assignment(ownership_engine):
    with Session(ownership_engine) as db:
        db.execute(text('UPDATE study_sessions SET owner_id = 2'))
        db.commit()
        with pytest.raises(ValueError, match='different account'):
            assign_legacy(db, 'alice@example.com', [10])
        assert db.execute(text('SELECT owner_id FROM decks WHERE id = 10')).scalar_one() is None
        assert db.execute(text('SELECT owner_id FROM study_sessions')).scalar_one() == 2


def test_assigned_records_cannot_be_reassigned(ownership_engine):
    with Session(ownership_engine) as db:
        assign_legacy(db, 'alice@example.com', [10])
        db.commit()
        with pytest.raises(ValueError, match='already belongs'):
            assign_legacy(db, 'bob@example.com', [10])
        assert db.execute(text('SELECT owner_id FROM decks WHERE id = 10')).scalar_one() == 1
