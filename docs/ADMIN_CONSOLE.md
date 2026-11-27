# Queezo Admin Console

The console runs inside the backend container. It has a dedicated password and an operator identifier for its audit records. It does not create a student account or an administrator role in the web app.

## Set up and sign in

From the repository root, run these commands in an interactive terminal. The first line updates both API services because both read the account schema. Keep the existing Compose project and data volume.

```powershell
docker compose up -d --build --wait
docker compose exec --user 0 backend python -m app.cli admin setup --operator ops_team
docker compose exec backend python -m app.cli admin
```

Replace `ops_team` with your operator label. Setup is available once and requires a dedicated password of 16–1024 characters. Enter it at the hidden prompt and store it in your password manager. Passwords are accepted only through the hidden terminal prompts. The database stores an Argon2id hash. Setup and recovery verify the container root identity and drop to the application user before using SQLite.

Inside the console, `help` lists commands, `whoami` shows the configured operator label, `clear` clears the terminal view, and `exit` closes the console. EOF or Ctrl+C at the command prompt also exits. After five minutes without a command the shell closes. Five unsuccessful attempts within the 15-minute login window cause further attempts to be rejected. The limit is shared across console launches.

## Commands

| Area | Read commands | Moderation commands |
| --- | --- | --- |
| Users | `users list`, `users search <query>`, `users inspect <username>` | `users suspend <username>`, `users unsuspend <username>`, `users revoke-sessions <username>`, `users changepassword <username>` |
| Decks | `decks list`, `decks inspect <id>` | `decks unpublish <id>`, `decks restore <id>` |
| Reports | `reports list`, `reports inspect <id>` | `reports resolve <id>`, `reports dismiss <id>` |
| Study Rooms | `rooms list`, `rooms inspect <uuid>` | `rooms close <uuid>` |
| System | `system status`, `system stats`, `system database`, `system backups` | |
| AI | `ai status`, `ai stats`, `ai cache-stats` | |
| Audit | `audit list`, `audit inspect <id>` | |

Lists and search support `--limit` (1–100, default 25) and `--offset` (default 0). User search matches usernames and display names. `users list` includes each account’s email and the boolean `email_verified`, which is currently always `false` because email verification is unavailable. The console prints JSON for command results.

All moderation commands require a printable `--reason` of up to 240 characters and an explicit `--yes`. Use `--dry-run` in place of `--yes` to evaluate the command and record a preview without persisting the moderation change.

```text
queezo-admin> users suspend example_user --reason "Account under review" --dry-run
queezo-admin> users suspend example_user --reason "Account under review" --yes
queezo-admin> users changepassword example_user --reason "Student locked out" --yes
queezo-admin> audit list --limit 10
```

- **Suspend** blocks sign-in and revokes all current sessions. Existing cookies are rejected on their next authenticated request and live sockets close on revalidation. Unsuspension permits a new sign-in. Suspension leaves published material subject to the usual visibility rules. Use deck moderation when the deck itself needs review.
- **Unpublish** withdraws a public or unlisted deck from sharing, including room access and shared Multiple-Choice sessions. It retains its original visibility setting, cards, ownership and history. The owner can still edit and study it. Restoration issues a fresh share link. An unpublished featured deck is removed from the profile and can be featured again after restoration. Copies already held by another user are independent.
- **Change password** sets a new password for a student account, then revokes all of its sessions so every device must sign in again. Run `users changepassword <username> --reason "..." --yes` and type the new password twice at the hidden prompt. It must meet the normal 11–1024-character rule and is hashed with the same Argon2 settings as sign-up, before the database write. `--dry-run` checks the account and records a preview without asking for a password. The inline form `users changepassword <username> <new-password> --reason "..." --yes` also works but prints a warning, because the password is visible on screen while you type it. The console keeps no command history, and passwords never appear in results, errors or the audit log, which stores only the operator, action, username, reason and outcome.
- **Resolve or dismiss** classifies a report and preserves it with its review timestamp. An existing final disposition cannot be overwritten.
- **Close room** stops active play, retains saved scores and round data, and removes pending invites. Connected participants discover the closure through existing room revalidation and receive the closure message on refresh. Invitation lists update on the normal notification poll. Participants who return later see the closure message. This does not send an out-of-band notice.

## Diagnostics and audit

System commands report SQLite health, journal settings, file allocation and persisted counts. `system backups` lists the local pre-migration snapshot count and the last reported backup date when the optional [backup overlay](production/DATABASE_RELIABILITY.md) is enabled. Only the success marker is exposed to the backend container. A missing marker means the scheduled status is unavailable. A reported date does not prove snapshots still exist or that a restore will succeed.

`ai status` checks the configured Ollama endpoint and the presence of the configured model without starting inference. AI statistics count available database snapshots and cache rows. Request latency, token usage, overall cache hit rate, and model-server logs are unavailable here.

Credential changes, login outcomes, moderation writes, rejected domain actions and previews are audited with the operator label, action, target, UTC timestamp, reason where applicable, and outcome. Read commands and invalid command syntax do not write audit rows. The database commits successful moderation and its audit row in one transaction. Audit records do not include passwords, session tokens, deck share links or card contents. Avoid entering secrets or unnecessary personal details in reason text.

## Rotate or recover access

Rotate with the current administrator password.

```powershell
docker compose exec backend python -m app.cli admin rotate
```

If it is lost, an authorized server operator with Docker root access can replace it without touching student credentials or records.

```powershell
docker compose exec --user 0 backend python -m app.cli admin recover --reason "Administrator credential lost" --yes
```

Both operations invalidate existing console logins. Recovery clears the login-attempt bucket and records the change as `server-root`. For database recovery, follow the [database runbook](production/DATABASE_RELIABILITY.md). A restored copy includes the administrator hash and audit rows from the snapshot. Recover the administrator credential before reopening access if its validity is uncertain.

## Operator boundary

Restrict operating-system logins, Docker access, and database and backup access to trusted operators. Docker or host access can reach the database directly. Legacy maintenance commands remain available to server operators. Audit rows are stored in SQLite and can be altered by someone with direct write access. Protect or export audit history separately if independent retention is required. The current console uses one configured operator credential and does not identify individual people sharing it.

Schema version 4 adds `admin_credential` and `admin_audit`, plus nullable moderation fields on users, decks and reports. Existing databases use the standard verified pre-migration backup before the additive update. See [schema initialization](../backend/app/database.py), [console](../backend/app/admin_cli.py) and [moderation service](../backend/app/services/admin.py).
