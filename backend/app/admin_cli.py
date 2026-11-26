"""Authenticated, allowlisted interactive operator console."""
import argparse
import json
import os
import re
import select
import shlex
import sys
from time import monotonic
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.auth.service import normalize_username
from app.database import SessionLocal, init_database
from app.services import admin
from app.services.admin_auth import (
    AdminError, authenticate, current_credential, normalized_reason, set_password, verify_principal,
)


IDLE_SECONDS = 300
MAX_LINE = 2048
HELP = """Commands
  users list | search <query> | inspect <username>
  users suspend | unsuspend | revoke-sessions <username>
  decks list | inspect <id> | unpublish <id> | restore <id>
  reports list | inspect <id> | resolve <id> | dismiss <id>
  rooms list | inspect <uuid> | close <uuid>
  system status | stats | database | backups
  ai status | stats | cache-stats
  audit list | inspect <id>
  help | clear | whoami | exit

Lists and search support --limit and --offset.
Moderation requires --reason "..." and --yes. Use --dry-run instead of --yes to preview.
"""


class CommandParser(argparse.ArgumentParser):
    def error(self, _message):
        raise AdminError('Invalid command or arguments. Type help for the command list.')


def bounded_int(value, minimum, maximum):
    if not re.fullmatch(r'[0-9]{1,19}', value) or not minimum <= int(value) <= maximum:
        raise argparse.ArgumentTypeError('Number out of range.')
    return int(value)


def identifier(value):
    return bounded_int(value, 1, 2**63 - 1)


def search_query(value):
    if not value.isprintable() or not 1 <= len(value.strip()) <= 80:
        raise argparse.ArgumentTypeError('Invalid search query.')
    return value.strip()


def room_id(value):
    return str(UUID(value))


def build_parser():
    parser = CommandParser(add_help=False, allow_abbrev=False)
    groups = parser.add_subparsers(dest='group', required=True)
    commands = {
        'users': {'list': None, 'search': None, 'inspect': normalize_username, 'suspend': normalize_username,
                  'unsuspend': normalize_username, 'revoke-sessions': normalize_username},
        'decks': {'list': None, 'inspect': identifier, 'unpublish': identifier, 'restore': identifier},
        'reports': {'list': None, 'inspect': identifier, 'resolve': identifier, 'dismiss': identifier},
        'rooms': {'list': None, 'inspect': room_id, 'close': room_id},
        'system': dict.fromkeys(('status', 'stats', 'database', 'backups')),
        'ai': dict.fromkeys(('status', 'stats', 'cache-stats')),
        'audit': {'list': None, 'inspect': identifier},
    }
    for group, actions in commands.items():
        root = groups.add_parser(group, add_help=False, allow_abbrev=False)
        verbs = root.add_subparsers(dest='action', required=True)
        for action, target in actions.items():
            command = verbs.add_parser(action, add_help=False, allow_abbrev=False)
            change = target is not None and action != 'inspect'
            command.set_defaults(change=change)
            if target:
                command.add_argument('target', type=target)
            if action in {'list', 'search'}:
                command.add_argument('--limit', type=lambda value: bounded_int(value, 1, 100), default=25)
                command.add_argument('--offset', type=lambda value: bounded_int(value, 0, 1_000_000), default=0)
            if action == 'search':
                command.add_argument('query', type=search_query)
            if change:
                command.add_argument('--reason', required=True)
                confirmation = command.add_mutually_exclusive_group(required=True)
                confirmation.add_argument('--yes', action='store_true')
                confirmation.add_argument('--dry-run', action='store_true')
    return parser


def parse_command(parser, line):
    try:
        words = shlex.split(line)
        return parser.parse_args(words)
    except ValueError:
        raise AdminError('Invalid command or arguments. Type help for the command list.') from None


def read_line(timeout):
    print('queezo-admin> ', end='', flush=True)
    if not select.select([sys.stdin], [], [], timeout)[0]:
        raise TimeoutError
    line = sys.stdin.readline(MAX_LINE + 1)
    if not line:
        raise EOFError
    if len(line) > MAX_LINE:
        # Leave the shell rather than execute any unread portion of a pasted line.
        raise AdminError('Command is too long. Console closed.')
    return line.strip()


def shell(factory, principal, *, reader=read_line):
    parser = build_parser()
    deadline = monotonic() + IDLE_SECONDS
    while True:
        try:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError
            command = reader(remaining)
            if monotonic() >= deadline:
                raise TimeoutError
        except TimeoutError:
            print('Console closed after five minutes of inactivity.')
            return 0
        except (EOFError, KeyboardInterrupt):
            print('\nConsole closed.')
            return 0
        if command == 'exit':
            return 0
        if not command:
            continue
        try:
            with factory() as db:
                verify_principal(db, principal)
        except AdminError as error:
            print(error, file=sys.stderr)
            return 1
        try:
            if command == 'help':
                print(HELP)
            elif command == 'clear':
                print('\033[2J\033[H', end='', flush=True)
            elif command == 'whoami':
                print(principal.operator)
            else:
                args = parse_command(parser, command)
                result = admin.execute(factory, principal, args)
                print(json.dumps(result, indent=2, ensure_ascii=True))
        except AdminError as error:
            print(error, file=sys.stderr)
        except SQLAlchemyError:
            print('Database command failed. No moderation change was committed.', file=sys.stderr)
        deadline = monotonic() + IDLE_SECONDS


def terminal_required():
    if os.name != 'posix' or not sys.stdin.isatty() or not sys.stdout.isatty():
        raise AdminError('Run the console in an interactive Docker terminal with input and output attached.')


def server_root():
    if os.geteuid() != 0:
        raise AdminError('Setup and recovery require a server operator using docker compose exec --user 0.')
    # Drop to the Docker application's user before opening the database or its WAL files.
    import pwd
    try:
        user = pwd.getpwnam('queezo')
    except KeyError:
        raise AdminError('Use the Queezo backend container for setup and recovery.') from None
    os.setgroups([])
    os.setgid(user.pw_gid)
    os.setuid(user.pw_uid)


def new_password(prompt):
    first = prompt('New administrator password (at least 16 characters): ')
    if first != prompt('Confirm administrator password: '):
        raise AdminError('Password confirmation did not match.')
    return first


def run(args, prompt):
    terminal_required()
    mode = args.admin_command
    if mode in {'setup', 'recover'}:
        server_root()
    init_database()
    credential = current_credential(SessionLocal)
    if mode == 'setup':
        if credential is not None:
            raise AdminError('Administrator is already configured. Use admin rotate or admin recover.')
        set_password(SessionLocal, mode, new_password(prompt), operator=args.operator)
        print('Administrator credential configured.')
        return 0
    if credential is None:
        raise AdminError('Administrator credential is not configured. Run admin setup.')
    if mode == 'recover':
        reason = normalized_reason(args.reason)
        set_password(SessionLocal, mode, new_password(prompt), expected=credential, reason=reason)
        print('Administrator credential recovered. Open consoles must sign in again.')
        return 0
    print('QUEEZO ADMIN CONSOLE\n')
    principal = authenticate(SessionLocal, prompt('Admin Password: '))
    print('Authentication successful.')
    if mode == 'rotate':
        credential = current_credential(SessionLocal)
        set_password(SessionLocal, mode, new_password(prompt), principal=principal, expected=credential)
        print('Administrator password rotated. Open consoles must sign in again.')
        return 0
    return shell(SessionLocal, principal)
