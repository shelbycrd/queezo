"""Interactive account provisioning and explicit legacy-data ownership tools."""
import argparse
import getpass
import json
import sys
import warnings

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.service import create_user
from app.database import engine, init_database
from app.ownership_migration import assign_legacy, list_unowned


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
    password = secure_password("Password (at least 12 characters): ")
    confirmation = secure_password("Confirm password: ")
    if password != confirmation:
        print("Account was not created: password confirmation did not match.", file=sys.stderr)
        return 1
    init_database()
    try:
        with Session(engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            user = create_user(db, email, password)
            created_email = user.email
            db.commit()
    except (ValueError, IntegrityError):
        print(
            "Account was not created. Check the email format, use at least 12 password characters, "
            "and ensure the email is not already registered.", file=sys.stderr
        )
        return 1
    print(f"Account created for {created_email}.")
    return 0


def main(argv=None):
    parser = SafeArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create-user", help="Prompt securely for a new account's credentials")
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
