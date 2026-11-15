import getpass
import warnings

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import cli
from app.database import init_database, make_engine
from app.models import Deck


@pytest.fixture
def cli_engine(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{(tmp_path / 'cli.db').as_posix()}")
    init_database(engine)
    monkeypatch.setattr(cli, 'engine', engine)
    monkeypatch.setattr(cli, 'init_database', lambda: None)
    yield engine
    engine.dispose()


def configure_prompts(monkeypatch, email='  CLI.User@EXAMPLE.COM ', passwords=None):
    passwords = iter(passwords or ['A secure test password 2026', 'A secure test password 2026'])
    prompts = []
    monkeypatch.setattr('builtins.input', lambda prompt: 'cli_user' if prompt.startswith('Username') else 'CLI User' if prompt.startswith('Display') else email)

    def password_prompt(prompt):
        prompts.append(prompt)
        return next(passwords)

    monkeypatch.setattr(cli.getpass, 'getpass', password_prompt)
    return prompts


def test_cli_creates_normalized_account_with_secure_prompts_and_no_secret_output(cli_engine, monkeypatch, capsys):
    prompts = configure_prompts(monkeypatch)
    assert cli.main(['create-user']) == 0
    assert len(prompts) == 2
    assert prompts[0].startswith('Password')
    assert prompts[1].startswith('Confirm password')
    captured = capsys.readouterr()
    assert 'Account created for cli.user@example.com.' in captured.out
    assert 'A secure test password 2026' not in captured.out + captured.err
    assert '$argon2' not in captured.out + captured.err
    with cli_engine.connect() as db:
        user = db.execute(text('SELECT email, password_hash FROM users')).mappings().one()
        assert user['email'] == 'cli.user@example.com'
        assert user['password_hash'].startswith('$argon2id$')


@pytest.mark.parametrize('email,passwords', [
    ('bad-email', ['A secure test password 2026'] * 2),
    ('valid@example.com', ['short'] * 2),
    ('valid@example.com', ['A secure test password 2026', 'Different confirmation 2026']),
])
def test_cli_invalid_or_unconfirmed_credentials_do_not_create_accounts(cli_engine, monkeypatch, capsys, email, passwords):
    configure_prompts(monkeypatch, email=email, passwords=passwords)
    assert cli.main(['create-user']) == 1
    output = capsys.readouterr()
    assert all(password not in output.out + output.err for password in passwords)
    with cli_engine.connect() as db:
        assert db.execute(text('SELECT COUNT(*) FROM users')).scalar_one() == 0


def test_cli_rejects_case_insensitive_duplicate_email(cli_engine, monkeypatch, capsys):
    configure_prompts(monkeypatch)
    assert cli.main(['create-user']) == 0
    configure_prompts(monkeypatch, email='CLI.USER@example.com')
    assert cli.main(['create-user']) == 1
    output = capsys.readouterr()
    assert 'not already registered' in output.err
    assert 'A secure test password 2026' not in output.out + output.err
    with cli_engine.connect() as db:
        assert db.execute(text('SELECT COUNT(*) FROM users')).scalar_one() == 1


def test_cli_refuses_getpass_echo_fallback(cli_engine, monkeypatch, capsys):
    monkeypatch.setattr('builtins.input', lambda prompt: 'valid@example.com')

    def insecure_prompt(prompt):
        warnings.warn('Password input may be echoed.', getpass.GetPassWarning)
        pytest.fail('getpass fallback must be stopped before reading echoed input')

    monkeypatch.setattr(cli.getpass, 'getpass', insecure_prompt)
    assert cli.main(['create-user']) == 1
    assert 'interactive terminal' in capsys.readouterr().err
    with cli_engine.connect() as db:
        assert db.execute(text('SELECT COUNT(*) FROM users')).scalar_one() == 0


def test_cli_cancelled_secure_prompt_creates_no_account(cli_engine, monkeypatch, capsys):
    monkeypatch.setattr('builtins.input', lambda prompt: 'valid@example.com')
    monkeypatch.setattr(cli.getpass, 'getpass', lambda prompt: (_ for _ in ()).throw(EOFError()))
    assert cli.main(['create-user']) == 1
    assert 'cancelled' in capsys.readouterr().err
    with cli_engine.connect() as db:
        assert db.execute(text('SELECT COUNT(*) FROM users')).scalar_one() == 0


def test_cli_inventory_and_explicit_legacy_assignment(cli_engine, monkeypatch, capsys):
    configure_prompts(monkeypatch)
    assert cli.main(['create-user']) == 0
    with Session(cli_engine) as db:
        deck = Deck(title='Preserved deck')
        db.add(deck)
        db.flush()
        identity = deck.id
        db.commit()
    capsys.readouterr()
    assert cli.main(['list-unowned']) == 0
    inventory = capsys.readouterr().out
    assert 'Preserved deck' in inventory
    assert cli.main(['assign-legacy', '--email', 'CLI.USER@example.com', '--deck-id', str(identity)]) == 0
    assert 'Assigned 1 deck(s)' in capsys.readouterr().out
    with cli_engine.connect() as db:
        owner = db.execute(text('SELECT owner_id FROM decks WHERE id = :id'), {'id': identity}).scalar_one()
        assert owner == db.execute(text('SELECT id FROM users')).scalar_one()
    assert cli.main(['assign-legacy', '--email', 'CLI.USER@example.com', '--deck-id', str(identity)]) == 1
    assert 'already belongs' in capsys.readouterr().err


def test_cli_has_no_plaintext_password_argument(capsys):
    with pytest.raises(SystemExit) as failure:
        cli.main(['create-user', '--password', 'not-an-accepted-option'])
    assert failure.value.code != 0
    output = capsys.readouterr()
    assert 'not-an-accepted-option' not in output.out + output.err
