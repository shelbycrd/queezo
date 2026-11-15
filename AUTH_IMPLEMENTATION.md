# Authentication implementation report

Implemented November 13, 2026, directly in the existing Queezo project.

## November 15 account creation update

Public signup is now available at `/#signup` and `POST /api/auth/signup`. It collects display name, unique case-insensitive username/email, an 11-character-minimum password, and matching confirmation. A local red/yellow/green strength estimate is advisory. Each user receives a random unique UUID, and signup signs the user in using the existing Argon2id/session protections. Trusted-origin checks, a 16 KiB request limit, and a persistent signup IP limiter protect the route.

CLI provisioning now also collects display name and username. `list-users`, `show-user`, `revoke-sessions`, and exact-UID-confirmed `delete-user` are available. Deletion removes only the selected account and its owned records. The additive profile migration preserved existing credentials, IDs, and academic data; all preexisting table columns/rows matched the backup after upgrade (2 accounts, 7 decks, 32 cards, 21 study sessions, 148 reviews).

The sections below document the original November 13 implementation; their CLI-only registration and 12-character minimum describe that earlier release. [AUTH_SETUP.md](AUTH_SETUP.md) is the current operator guide. Email verification, password recovery/reset, and a web admin interface remain unimplemented.

## Result

The local Docker stack is running with a theme-matched login form and logout control. Accounts can only be provisioned by the CLI. There is no signup, reset, account-deletion endpoint, or admin interface. App 1 and App 2 retain their routes, calculations, study behavior, and layouts behind authentication.

Passwords are Argon2id hashes with independent salts (64 MiB, three iterations, four lanes). The CLI validates and normalizes email addresses, enforces case-insensitive uniqueness and a 12-character minimum, prompts twice using secure input, and refuses echoed-input fallback. It accepts no password arguments.

Successful login creates a random 256-bit opaque token with fixed seven-day expiry. The database stores its SHA-256 hash. The cookie is HttpOnly, SameSite=Lax, host-only, and Secure in HTTPS mode; production also uses the `__Host-` prefix. Logout deletes the server-side session and cookie. Session-bound CSRF tokens stay only in frontend memory and are checked on all authenticated mutations. Login uses strict JSON, trusted-origin/Fetch-Metadata checks, generic credential errors, and persistent email/IP limits (5/30 attempts per 15 minutes). Expired throttle rows are pruned; blocked clients cannot create unlimited new email buckets.

Auth dependencies scope academic queries to the authenticated owner, including child-card/session joins. Other accounts' and unassigned legacy resources return 404. GWA remains stateless but validates the same session through the shared SQLite volume. API responses use no-store caching. Nginx adds anti-framing headers and sanitizes proxy client-IP headers; backend ports remain internal.

Frontend login restores cookies via `/api/auth/me`, carries CSRF headers, redirects expired sessions, and rejects responses from older account contexts. Pomodoro local storage is namespaced by account, anonymous legacy state is preserved without adopting it, and logout pauses timers and clears visible/pending notifications.

## Migration and preservation

Migration is additive and repeatable: create auth tables, add nullable `owner_id` columns/indexes to decks and study sessions, and retain all existing cards, sessions, snapshots, and reviews. Existing records remain ownerless and inaccessible through account APIs until an operator deliberately runs `assign-legacy` for selected deck IDs. Creating a user never claims data.

Verified live counts before and after: 2 decks, 8 cards, 2 study sessions, 43 reviews. Zero real users created and zero legacy owners assigned. Backups exist in `/data/queezo-before-auth-20261113.db` and `outputs/backups/queezo-before-auth-20261113.db`.

## Changed and added files

- Backend security/configuration: `backend/app/auth/__init__.py`, `config.py`, `service.py`, `dependencies.py`, `router.py`, `middleware.py`.
- Backend integration/ownership: `backend/app/models.py`, `database.py`, `main.py`, `routers/decks.py`, `routers/study.py`, `gwa/main.py`.
- CLI and migration: `backend/app/cli.py`, `backend/app/ownership_migration.py`.
- Backend dependencies/build: `backend/requirements.txt`, `backend/Dockerfile`.
- Backend tests: `backend/tests/conftest.py`, `test_gwa.py`, `test_auth.py`, `test_cli.py`, `test_ownership_migration.py`, `manual_auth_http.py`.
- Frontend authentication: `frontend/js/auth-state.js`, `auth.js`, `api.js`, `app.js`; `frontend/index.html`; `frontend/css/auth.css`.
- Pomodoro account isolation: `frontend/js/pomodoro.js`.
- Frontend tests: `frontend/tests/auth-client.test.mjs`, `pomodoro-account.test.mjs`.
- Gateway and deployment: `nginx/nginx.conf`, `nginx/security-headers.conf`, `nginx/Dockerfile`, `compose.yaml`, `.env.example`.
- Documentation: `README.md`, `AUTH_SETUP.md`, `AUTH_IMPLEMENTATION.md`, `VERIFICATION.md`.
- Local verification artifacts: `outputs/queezo-login-preview.jpg` and the private pre-authentication backup under `outputs/backups/`.

## Validation

**324 backend tests passed** in Docker, including existing Flashcards and GWA regressions. **30 frontend tests passed**, including original Pomodoro tests and new auth/privacy race tests. Syntax, Compose validation, image builds, all service health checks, and Nginx validation passed. One dependency deprecation warning remains in Starlette's AnyIO type alias; it did not affect results.

Interactive CLI provisioning, password non-echo, login/logout, generic errors, seven-day cookie expiry, CSRF, server restart persistence, expired-session UI, replay rejection, and live HTTP academic flows were checked using an isolated disposable stack. Cross-account read/write isolation and safe explicit legacy assignment were covered by backend tests. Seven-day expiration is verified with recorded deadlines and controlled boundary timestamps, not a seven-day wait.

The isolated stack and its accounts were removed. No test credentials or real accounts remain in the live database. No authentication tokens are stored in localStorage.

## Required operator steps and limitations

1. Create your first real account: `docker compose exec backend python -m app.cli create-user`.
2. Log in at `http://localhost:8080`.
3. Inspect preserved data using `python -m app.cli list-unowned` inside the backend, then explicitly assign only the correct deck IDs. See `AUTH_SETUP.md` for full commands.

The default Compose configuration is for local HTTP development. Production requires your own HTTPS/TLS endpoint, `AUTH_ENV=production`, `AUTH_COOKIE_SECURE=true`, and exact HTTPS trusted origins. That deployment was not attempted; production cookie behavior was tested through HTTPS TestClient requests. Keep backend ports unpublished because the container commands trust forwarding headers from their internal proxy network.

Pomodoro data remains browser-local and is not encrypted or server-stored; account namespacing protects normal UI access, not access by someone who can inspect a shared browser profile. Original anonymous timer data remains in its original local store, without being assigned to an arbitrary account. Existing academic records remain private and unassigned until explicitly selected through the CLI.

There are no known failing tests or blocked implementation items. First-account provisioning and legacy ownership selection are intentionally left to the operator, since no account identity or ownership mapping was provided.
