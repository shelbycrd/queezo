# Queezo

**Study with flashcards, calculate your GWA, and make time to focus.**

![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Local%20setup-Docker%20Compose-2496ED?logo=docker&logoColor=white)

Queezo is a study workspace for students. Build your own decks, discover decks shared by other students, check a unit-weighted grade average, and work through a task list with a Pomodoro timer. The app runs locally with Docker Compose.

## What you can do

| App | Features |
| --- | --- |
| **Flashcards** | Create two-sided cards with optional photos and typed lists. Search and sort decks. Run a timed or unlimited study session with immediate answer reveal, difficulty ratings, and a review summary. |
| **GWA Calculator** | Calculate `sum(grade × units) / sum(units)` for 1–15 courses on a 1.00–5.00 scale. Subject names are optional. Enter `175` as shorthand for `1.75`. Results include a classification and a grade-scale bar. Calculations are stateless. |
| **Pomodoro Timer** | Customize study and break lengths, set study targets for tasks, and see alerts when intervals or tasks finish. The default is four 25-minute study sessions with three 5-minute breaks and a 15-minute long break. Each new phase waits for you to start it. |

Decks default to **Private**. **Public** decks appear in Community Decks on Home, which shows up to 20 recent decks, and on the owner's profile. **Unlisted** decks are accessible by share link. Sharing requires sign-in, and readers can save an independent private copy. The deck editor requires a question and answer and rejects URLs in titles and card text.

Rated flashcards and completed study intervals count toward streaks using Asia/Manila calendar days. Profile shows your total decks and longest streak. Pomodoro settings and tasks stay in the current browser under your account. In-app alerts work while Queezo is open, and desktop alerts require browser permission.

The Friends area is marked **Coming soon**, and chat is a local preview. Email verification and password recovery are unavailable.

## Getting started

Install and start [Docker Desktop](https://docs.docker.com/desktop/) with Linux containers, or use Docker Engine with the Compose plugin. The first build needs internet access to fetch container images and Python dependencies.

From the repository root in PowerShell:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose config --quiet
docker compose up -d --build --wait
docker compose ps
```

Open [Queezo on localhost](http://localhost:8080) and choose **Create an account**. Usernames and email addresses are unique regardless of capitalization. Passwords require at least 11 characters. After signing in, choose **Flashcards**, **GWA Calculator**, or **Pomodoro** in the sidebar. In study mode, use **Enter** to reveal and **1**, **2**, or **3** to rate Hard, Normal, or Easy.

The defaults in [`.env.example`](.env.example) are for local HTTP. If you change `APP_PORT` or the browser hostname, update `AUTH_TRUSTED_ORIGINS` to match the exact origins, including the port. See the [account setup guide](AUTH_SETUP.md#environment-configuration) for HTTPS settings.

You can also create an account from an interactive terminal:

```powershell
docker compose exec backend python -m app.cli create-user
```

The CLI also supports listing and inspecting users, revoking sessions, deleting accounts, and assigning legacy decks. See the [CLI and legacy ownership instructions](AUTH_SETUP.md).

## Tech stack and project structure

| Path | Role |
| --- | --- |
| [`frontend/`](frontend/) | HTML, CSS, and browser JavaScript. Includes all screens, the Pomodoro timer, and frontend tests. |
| [`backend/app/`](backend/app/) | Python 3.12 and FastAPI for accounts, flashcards, sharing, study sessions, and activity. |
| [`backend/app/gwa/`](backend/app/gwa/) | Separate FastAPI service for decimal-based GWA calculations. |
| [`backend/tests/`](backend/tests/) | Pytest coverage for API behavior, accounts, persistence, and migrations. |
| [`nginx/`](nginx/) and [`compose.yaml`](compose.yaml) | Nginx serves the frontend and proxies both APIs. Compose runs the three services. |

Both APIs use SQLAlchemy and a shared SQLite database for account and session validation. Passwords are hashed with Argon2id, and authenticated writes use CSRF checks. The Compose database is stored in the `queezo_data` volume. `docker compose down` keeps it. **`docker compose down -v` deletes it.**

## Development and operations

```powershell
docker compose up -d --build --no-deps --wait frontend  # Frontend changes
# Rebuild all services after backend changes.
docker compose up -d --build --wait
docker compose logs --tail=100 backend gwa frontend
```

For API-only development outside Docker, activate a Python 3.12 virtual environment, open `backend/`, and run `python -m pip install -r requirements.txt`. Set the following variables in each of two PowerShell terminals in `backend/`, then start one Uvicorn service per terminal. Both services use the same default local SQLite file when started from that directory.

```powershell
$env:AUTH_ENV = 'development'
$env:AUTH_COOKIE_SECURE = 'false'
$env:AUTH_TRUSTED_ORIGINS = 'http://127.0.0.1:8000,http://127.0.0.1:8001'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# In the second terminal, after setting the same three variables:
python -m uvicorn app.gwa.main:app --host 127.0.0.1 --port 8001
```

The standalone API docs are at `http://127.0.0.1:8000/docs` and `http://127.0.0.1:8001/gwa/docs`.

### Upgrading an older database

Back up the database before upgrading. The [legacy ownership guide](AUTH_SETUP.md#existing-decks-are-preserved) explains how to assign existing unowned decks. If Flashcards startup reports one-sided cards or snapshots, inspect the affected IDs:

```powershell
docker compose build backend
docker compose run --rm --no-deps backend python -m app.migrate_cards
```

Create `answers.json` at the repository root with the reported IDs and an explicit answer for each. Use the applicable groups `flashcards` and `study_session_cards`, for example `{"flashcards":{"1":"Card answer"},"study_session_cards":{"9":"Snapshot answer"}}`. Apply the conversion, then restart:

```powershell
docker compose run --rm --no-deps -v "${PWD}/answers.json:/tmp/answers.json:ro" backend python -m app.migrate_cards --answers /tmp/answers.json
docker compose up -d --build --wait
```

## Documentation

- Local API references for [Flashcards and accounts](http://localhost:8080/docs) and [GWA](http://localhost:8080/gwa/docs). Health endpoints are `/api/health` and `/api/gwa/health`.
- [Account setup and troubleshooting](AUTH_SETUP.md) and [authentication implementation](AUTH_IMPLEMENTATION.md).
- [Verification history](VERIFICATION.md) and [visual asset attribution](frontend/assets/README.md).

## Contributing

Open a GitHub issue with reproduction steps, expected behavior, and relevant logs or screenshots. Leave out credentials, cookies, share tokens, and private study data. For a pull request, keep changes focused and describe how you checked them. Run the relevant checks from the repository root:

```powershell
docker compose run --rm --no-deps backend python -m pytest -q
node --test frontend/tests/*.test.mjs
```

The backend suite uses temporary test databases. The frontend suite uses Node.js's built-in test runner.

## License

The repository does not contain a project-wide license. The bundled Quicksand font has its own [SIL Open Font License](frontend/assets/fonts/OFL-Quicksand.txt).
