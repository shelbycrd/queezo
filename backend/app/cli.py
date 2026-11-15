"""Interactive account provisioning and explicit legacy-data ownership tools."""
import argparse
import getpass
import json
import sys
import warnings

from sqlalchemy import text, select, delete, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.service import create_user
from app.database import engine, init_database
from app.ownership_migration import assign_legacy, list_unowned
from app.models import User, AuthSession, Deck, StudySession, ActivityDay


class InsecurePasswordInput(RuntimeError):
    pass


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default includes unexpected argument values. If someone
        # mistakenly supplies a password flag, do not echo its value back.
        self.print_usage(sys.stderr)
        self.exit(2, "Invalid command or arguments. Use --help. Passwords are accepted only through secure prompts.\n")


def secure_password(prompt):
    # getpass normally falls back to echoed stdin when no terminal is present.
    # Treat that warning as an error before it can read any password insecurely.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt)
    except getpass.GetPassWarning:
        raise InsecurePasswordInput(
            "Secure password entry is unavailable. Use an interactive terminal without redirected input."
        ) from None


def provision_user():
    email = input("Email: ").strip()
    display_name = input("Display name: ").strip()
    username = input("Username: ").strip()
    password = secure_password("Password (more than 10 characters): ")
    confirmation = secure_password("Confirm password: ")
    if password != confirmation:
        print("Account was not created: password confirmation did not match.", file=sys.stderr)
        return 1
    init_database()
    try:
        with Session(engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            user = create_user(db, email, password, username=username, display_name=display_name)
            created_email = user.email
            db.commit()
    except (ValueError, IntegrityError):
        print(
            "Account was not created. Check the account fields, use more than 10 password characters, "
            "and ensure the email and username are not already registered.", file=sys.stderr
        )
        return 1
    print(f"Account created for {created_email}.")
    return 0


def account_view(user):
    return {'uid':user.uid, 'username':user.username, 'display_name':user.display_name,
            'email':user.email, 'created_at':user.created_at.isoformat() + 'Z'}


def manage_accounts(args):
    with Session(engine) as db:
        if args.command == 'list-users':
            print(json.dumps([account_view(user) for user in db.scalars(select(User).order_by(User.created_at,User.id))], indent=2))
            return 0
        db.execute(text('BEGIN IMMEDIATE'))
        user = db.scalar(select(User).where(User.uid == args.uid))
        if user is None:
            raise ValueError('No account has that UID.')
        if args.command == 'show-user':
            result = account_view(user)
            result['deck_count'] = db.scalar(select(func.count()).select_from(Deck).where(Deck.owner_id == user.id))
            result['session_count'] = db.scalar(select(func.count()).select_from(AuthSession).where(AuthSession.user_id == user.id))
            print(json.dumps(result, indent=2))
            return 0
        if args.command == 'delete-user':
            confirm = args.confirm if args.confirm is not None else input(f'Permanently delete {user.username} and their decks/history? Type UID {user.uid}: ').strip()
            if confirm != user.uid:
                raise ValueError('UID confirmation did not match. Nothing was deleted.')
        count = db.execute(delete(AuthSession).where(AuthSession.user_id == user.id)).rowcount
        if args.command == 'delete-user':
            db.execute(delete(StudySession).where(StudySession.owner_id == user.id))
            db.execute(delete(Deck).where(Deck.owner_id == user.id))
            db.execute(delete(ActivityDay).where(ActivityDay.user_id == user.id))
            db.delete(user)
            db.commit()
            print(f'Account {args.uid} and its owned data were deleted.')
        else:
            db.commit()
            print(f'Revoked {count} session(s) for {args.uid}.')
        return 0


def main(argv=None):
    parser = SafeArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create-user", help="Prompt securely for a new account's credentials")
    commands.add_parser('list-users', help='List account identities without passwords or session secrets')
    for command, help_text in [('show-user','View one account'),('delete-user','Permanently delete an account and owned data'),('revoke-sessions','Log an account out on all devices')]:
        command_parser = commands.add_parser(command, help=help_text)
        command_parser.add_argument('--uid', required=True)
        if command == 'delete-user':
            command_parser.add_argument('--confirm', help='Repeat the exact UID to confirm deletion; otherwise prompts')
    commands.add_parser("list-unowned", help="List preserved legacy decks that have no account owner")
    assignment = commands.add_parser("assign-legacy", help="Assign explicitly selected unowned decks to an existing account")
    assignment.add_argument("--email", required=True, help="Existing account email")
    assignment.add_argument("--deck-id", action="append", type=int, required=True,
                            help="Unowned deck ID; repeat this option to select multiple decks")
    args = parser.parse_args(argv)
    try:
        if args.command == "create-user":
            return provision_user()
        init_database()
        if args.command in {'list-users','show-user','delete-user','revoke-sessions'}:
            return manage_accounts(args)
        with Session(engine) as db:
            if args.command == "list-unowned":
                print(json.dumps(list_unowned(db), indent=2))
                return 0
            db.execute(text("BEGIN IMMEDIATE"))
            result = assign_legacy(db, args.email, args.deck_id)
            db.commit()
            print(f"Assigned {result['deck_count']} deck(s) and {result['session_count']} "
                  f"study session(s) to {result['email']}.")
            return 0
    except InsecurePasswordInput as exc:
        print(str(exc), file=sys.stderr)
    except (KeyboardInterrupt, EOFError):
        print("Command cancelled. No account was created.", file=sys.stderr)
    except ValueError as exc:
        # This branch handles ownership selection errors, not password inputs.
        print(str(exc), file=sys.stderr)
    except (RuntimeError, SQLAlchemyError):
        print("Command failed. Check database availability and the migration instructions in AUTH_SETUP.md.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
