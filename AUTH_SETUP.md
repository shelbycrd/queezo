# Account setup

Queezo requires an account to use its study apps. Users can register on the website or an operator can create accounts through the backend CLI. Account deletion and session revocation are operator CLI commands. Email verification, password recovery, password resets, and a web admin page are not implemented.

## Start locally

Open PowerShell in `C:\Users\User\Desktop\Queezo` with Docker Desktop running:

```powershell
# Create .env only if you do not already have one.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build --wait
```

The supplied Compose configuration is for local HTTP development at `http://localhost:8080`. Both academic backends use the same SQLite volume for account/session validation. GWA calculation remains stateless; it does not save academic records.

## Create your first account

Open `http://localhost:8080/#signup` or choose **Create an account** on the login page. Enter:

- Display name: 1–80 characters; other users may use the same name.
- Username: 3–32 letters, numbers, or underscores; unique without regard to capitalization.
- Email: a valid address, unique without regard to capitalization.
- Password: more than 10 characters (**11 minimum**, at most 1,024).
- Confirm password: must match exactly.

The red/yellow/green meter gives an advisory estimate only. It recommends 12 or more characters, varied character types, and avoiding common words, sequences, repeated patterns, and personal information. It does not add composition requirements or send passwords to a strength-checking service. A long, unique password or passphrase is preferable to a predictable substitution pattern; see [OWASP authentication guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html). The estimate is a reminder, not a guarantee.

**Sign up** saves the account and signs the user in. Each account receives a random unique UUID shown on **Profile** and in CLI listings. No default credentials are created automatically.

Alternatively, run this in an interactive terminal:

```powershell
docker compose exec backend python -m app.cli create-user
```

Enter your email, display name, username, password of at least **11 characters**, and password confirmation. Password input stays invisible, including the cursor: type normally and press Enter. The CLI refuses terminals that would echo passwords. Do not add `-T`, pipe input, or supply a password as a command argument.

Emails and usernames are normalized before validation, with database uniqueness guards to handle concurrent requests. Duplicate email/username, invalid fields, short passwords, and mismatched confirmation create no account. Signup requests are restricted to trusted origins and limited to 10 attempts per client IP in 15 minutes.

Open `http://localhost:8080`, log in with the account you just created, and use **Log out** when finished. Login opens the dashboard; refreshing restores a valid login and keeps the current authenticated page.

## Manage accounts from the CLI

Run these from the project directory. Replace `UID` with an actual UID from `list-users`:

```powershell
docker compose exec backend python -m app.cli list-users
docker compose exec backend python -m app.cli show-user --uid UID
docker compose exec backend python -m app.cli revoke-sessions --uid UID
docker compose exec backend python -m app.cli delete-user --uid UID
```

Listings include UID, username, display name, email, and creation time, with no password hashes or session secrets. `show-user` also reports deck and session counts. `revoke-sessions` signs that account out on all devices without deleting study content.

`delete-user` prompts for the exact UID. It permanently deletes the account, its login sessions, decks, cards, study history, and server activity records. Other accounts and unassigned legacy decks are preserved. Browser-local Pomodoro files are not remotely erased. For deliberate noninteractive deletion, pass `--confirm UID` with the same UID; keep a database backup before deleting anything you might need later.

Existing accounts keep their email, password, internal ID, and owned data. The additive profile migration assigns missing random UIDs, available `user_<id>` usernames, and display names based on the email prefix. Existing complete profiles are left intact. Profile and `list-users` show the assigned identities; editing these identities is not yet exposed in the website.

Before the November 15 signup upgrade, a consistent backup was saved at `/data/queezo-before-signup-20261115.db`, also copied to `outputs/backups/queezo-before-signup-20261115.db`. The upgrade preserved all original columns and rows for 2 users, 7 decks, 32 cards, 21 study sessions, and 148 reviews. Backups contain private data and password hashes; keep them out of Git.

## Existing decks are preserved

The ownership migration adds nullable ownership columns and indexes without deleting or rebuilding academic tables. Pre-account decks and study sessions stay **unassigned**; no account can read them until an operator explicitly assigns selected decks. Your first account's dashboard will therefore be empty even when old data exists.

Inspect the preserved decks:

```powershell
docker compose exec backend python -m app.cli list-unowned
```

After checking which account should own a deck, assign only its listed ID. Replace the example email and ID with your choices:

```powershell
docker compose exec backend python -m app.cli assign-legacy --email you@example.com --deck-id 2
```

Repeat `--deck-id` to select additional decks in the same command. Associated study sessions, cards, snapshots, and reviews are preserved. The command rejects nonexistent accounts/decks, already-owned decks, or conflicting session owners; it does not reassign another account's data.

A pre-upgrade backup was created at `/data/queezo-before-auth-20261113.db` in the backend volume. The pre-upgrade inventory contained 2 decks, 8 cards, 2 study sessions, and 43 reviews. To keep an additional host copy:

```powershell
docker compose cp backend:/data/queezo-before-auth-20261113.db .\queezo-before-auth-20261113.db
```

A host copy was also saved at `outputs/backups/queezo-before-auth-20261113.db`. Treat backups as private academic data.

`docker compose down` preserves data. **`docker compose down -v` deletes the database volume and its backup.**

## How login works

- Passwords use **Argon2id** with random salts, 64 MiB memory, 3 iterations, and 4 parallel lanes. The database stores hashes, never plaintext or reversible encryption.
- Login issues a cryptographically random opaque session token. Only its SHA-256 hash is stored server-side. No authentication token is stored in browser localStorage.
- Sessions expire **7 days after login**, including across page refreshes and backend restarts. Activity does not extend that deadline. Expiration redirects you to login; logout immediately revokes the session on the server.
- Session cookies are HttpOnly, SameSite=Lax, host-only, and Secure in HTTPS mode. Production uses the `__Host-` cookie prefix.
- `/api/auth/me` restores the user and a session-bound CSRF token. The frontend keeps CSRF information in memory and sends it on state-changing requests. The server also checks request origins.
- Login errors do not reveal whether an account exists. Persistent rate limits return HTTP 429 and a retry delay after excessive attempts.
- All academic data routes require authentication. Ownership is enforced in SQL queries. Health checks and API documentation remain public; public documentation does not grant access to private data.

Pomodoro tasks remain browser-local, namespaced by account ID. Logout stops that account's timer display and clears its visible notifications. The old anonymous Pomodoro storage is not assigned to a new account. Browser-local task data is not encrypted or synced to the server; use separate browser/OS profiles when sharing a device with people who can inspect its storage.

## Environment configuration

Edit `.env`, then rebuild/restart with `docker compose up -d --build --wait`.

| Variable | Local HTTP | HTTPS production |
| --- | --- | --- |
| `AUTH_ENV` | `development` | `production` |
| `AUTH_COOKIE_SECURE` | `false` | `true` — required |
| `AUTH_TRUSTED_ORIGINS` | `http://localhost:8080,http://127.0.0.1:8080` | Exact HTTPS origin, such as `https://study.example.com` |
| `APP_PORT` | `8080`, or your chosen port | Internal gateway port behind HTTPS termination |
| `DATABASE_URL` | Set by Compose to `sqlite:////data/queezo.db` | Shared persistent database path for both backends |

Origins are comma-separated exact values including nondefault ports, without paths or wildcards. If you change `APP_PORT`, also update the allowed local origins. Access through a different hostname requires adding that exact origin.

The Python application defaults to production with Secure cookies and refuses missing origins or insecure production configuration. Compose explicitly selects development settings for local use. No signing-secret environment variable is needed: sessions are random server-side records, not signed client tokens.

Production requires a separately configured HTTPS reverse proxy/TLS endpoint; this Compose file does not provide certificates or HTTPS. Keep backend ports unpublished. Uvicorn trusts the private container proxy path, and Nginx overwrites forwarded client-IP headers. If an additional proxy terminates TLS, configure Nginx to trust only that proxy's real-IP information so rate limits use the correct client IP. Never expose the backend directly or trust client-supplied forwarding headers.

## Troubleshooting and tests

- **Cannot log in:** create an account on the website or with the CLI first. Check the email/password; login still uses email, and generic errors deliberately do not identify which was wrong.
- **Secure password entry unavailable:** use ordinary interactive PowerShell and the command above without redirected input or `-T`.
- **Login succeeds but immediately disappears:** HTTP development needs `AUTH_ENV=development` and `AUTH_COOKIE_SECURE=false`. Production requires HTTPS and Secure cookies.
- **Origin/CSRF error:** open the exact configured hostname and port; check `.env`, restart services, and refresh the page.
- **Too many attempts:** wait for the displayed retry period, up to the 15-minute limiter window.
- **Old decks missing:** run `list-unowned`, then explicitly assign only the correct decks as described above.
- **Session expired:** log in again. Password recovery and resets are not implemented.

Run backend authentication and regression tests against temporary databases, plus frontend tests:

```powershell
docker compose run --rm --no-deps backend python -m pytest -q
node --test frontend/tests/*.test.mjs
docker compose ps
docker compose logs --tail=100 backend gwa frontend
```

Do not paste passwords or session-cookie values into logs, screenshots, or support messages.
