# Queezo study apps

Two independently runnable FastAPI apps share this repository:

- **App 1 — Flashcards:** `app.main:app`, persistent decks, two-sided cards, and resumable recall practice.
- **App 2 — GWA Calculator:** `app.gwa.main:app`, a stateless weighted-average calculator. It uses the shared database for authentication, without storing calculation records. App 2 currently implements GWA rather than Notes management.
- **App 3 — Pomodoro Timer:** a browser-based timer and task queue at `/#pomodoro`. It runs locally in the frontend and stores its state in this browser, without a separate backend service.

The lightweight frontend prototype provides an Apps page, two-sided Flashcards, a GWA Calculator connected to App 2, and a Pomodoro Timer. Open `http://localhost:8080` after starting Docker. GWA calculations and unfinished course entries are not saved across navigation or refresh; Pomodoro settings, task progress, and timer state are saved locally in the browser.

## Accounts and private data

Accounts are created exclusively through the secure CLI. There is no public signup or password-recovery page. After starting Docker, create your account in an interactive PowerShell terminal:

```powershell
docker compose exec backend python -m app.cli create-user
```

Enter a valid email and a password of at least 12 characters, then confirm it. Passwords stay hidden in the terminal. Log in at `http://localhost:8080`; the session lasts seven days and survives refreshes and backend restarts. **Log out** revokes it immediately.

Flashcards and study history are isolated by account using backend SQL ownership checks. GWA calculation also requires login and remains stateless. Existing records are preserved as unassigned legacy data; they do not automatically belong to the first account. To inspect and explicitly assign selected old decks, see [AUTH_SETUP.md](AUTH_SETUP.md). That guide also covers HTTPS production settings, cookie security, troubleshooting, and the pre-authentication backup.

## Run with Docker

Open Docker Desktop with its Linux engine running, then run from this folder:

```powershell
docker compose up -d --build --wait
docker compose ps
```

The `backend` service runs App 1, `gwa` runs App 2, and Nginx routes both APIs through port 8080. Change `APP_PORT` in `.env` if needed (see `.env.example`).

- Flashcards API documentation: `http://localhost:8080/docs`
- GWA API documentation: `http://localhost:8080/gwa/docs`
- Flashcards health: `GET /api/health`
- GWA health: `GET /api/gwa/health`
- Login / logout: `POST /api/auth/login`, `POST /api/auth/logout`
- Restore current session: `GET /api/auth/me`

The first build needs internet to download images and Python dependencies.

### Try the frontend prototype

Choose **Flashcards** to create a deck and add a required question and answer. Reveal the answer before rating your recall. The removed one-sided option is no longer shown.

Choose **GWA Calculator**, enter units and grades for at least one course, and select **What's my GWA?** Subject names are optional. **Add course** and **Remove** keep the list between 1 and 15 courses. **Clear** starts a new calculation. The summary shows your GWA, honor standing, performance, total units, and a 0–100 grade-scale bar. Editing inputs hides the previous summary until you recalculate.

Choose **Pomodoro** to add tasks with a target number of study intervals, then select **Start**. Timer settings default to 25 / 5 / 15 minutes and can be changed under **Timer settings**. The timer automatically alternates study and breaks and moves through the task queue without confirmation.

After source changes, rebuild with `docker compose up -d --build --wait frontend`, then refresh the browser (Ctrl+F5 if it still shows the previous version).

For independent development, install `backend/requirements.txt` in a Python 3.12 virtual environment, then run these commands in separate terminals from `backend/`:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python -m uvicorn app.gwa.main:app --host 127.0.0.1 --port 8001
```

Documentation is then at `http://localhost:8000/docs` and `http://localhost:8001/gwa/docs` respectively.

## App 1: Flashcards

All cards require a nonblank front and back, each at most 10,000 characters. `card_type` can be omitted and defaults to `two_sided`. If supplied, only `two_sided` is accepted. Creation and updates reject `one_sided`, null sides, and blank sides with HTTP 422. Partial updates keep omitted fields.

Example body for `POST /api/decks/{deck_id}/cards`:

```json
{
  "front": "What does GWA stand for?",
  "back": "General Weighted Average"
}
```

Deck/card routes retain `/api/decks`, `/api/decks/{id}/cards`, and `/api/cards/{id}`. Decks hold at most 150 cards. Dashboard counts and the latest 50 sessions per deck remain available.

Start practice with `POST /api/decks/{id}/study`. Use the returned `presentation_number` and `presentation_token` in `POST /api/study/{id}/reveal`, then include those identifiers and `difficulty` in `POST /api/study/{id}/rate`. Ratings are `easy`, `normal`, or `hard`. Answers are omitted from study responses before reveal. Rating before reveal or submitting stale/duplicate identifiers returns HTTP 409. There is no one-sided readiness flow.

`GET /api/study/{id}` resumes a session; `/exit` explicitly closes it; `/summary` returns a completed/exited summary. Session snapshots preserve original questions/answers across card edits and deletions. Deleting a deck also deletes its cards and study history.

The scheduler shuffles first encounters and uses latest-rating targets of 2 / 3 / 4 total reviews for Easy / Normal / Hard. Eligible repeats have weights 1 / 2 / 3 and virtual-position gaps of 5–8 / 3–5 / 1–3. It avoids consecutive repeats when another incomplete card exists, advances virtual positions when necessary, and completes within four times the initial card count. This is within-session practice; it does not schedule future study days. Duration includes idle time.

### Existing databases and removed one-sided cards

New databases enforce two-sided cards through NOT NULL and CHECK constraints. Startup installs INSERT/UPDATE guards on both card and snapshot tables, including in older databases where SQLite `create_all` cannot replace old constraints.

If old cards or session snapshots lack an answer or use the removed type, App 1 stops startup with their IDs. No questions, answers, or study history are deleted or automatically filled. Supply explicit answers before restarting. App 2 runs independently of this conversion.

First build the updated backend and inspect the IDs:

```powershell
docker compose build backend
docker compose run --rm --no-deps backend python -m app.migrate_cards
```

Create `answers.json` containing every reported ID, grouped by table. For example:

```json
{
  "flashcards": {"1": "Answer for the current card"},
  "study_session_cards": {"9": "Answer for the saved historical prompt"}
}
```

Use the actual reported IDs. Tables with no reported rows may be omitted. Historical snapshots require their own explicit answers because their prompts may differ from current cards. Apply the conversion from PowerShell in the project folder:

```powershell
docker compose run --rm --no-deps -v "${PWD}/answers.json:/tmp/answers.json:ro" backend python -m app.migrate_cards --answers /tmp/answers.json
docker compose up -d --build --wait
```

The conversion validates all answers before writing and commits atomically. Incomplete mappings, unexpected IDs, and invalid answers leave existing content unchanged.

## App 2: GWA Calculator

`POST /api/gwa/calculate` implements the future **What's my GWA?** action. Send between **1 and 15 courses**:

```json
{
  "courses": [
    {"subject": "Mathematics", "units": 3, "grade": 1.25},
    {"units": 2, "grade": 2.0}
  ]
}
```

- `subject` is optional, at most 120 characters; blank/null subjects become null.
- `units` must be positive. Fractional units are accepted, with up to four decimal places and twelve digits total (at most eight integer digits).
- `grade` must be between **1.00 and 5.00**, inclusive, with up to six decimal places.
- Numeric JSON values or decimal strings are accepted. Missing required fields, booleans, nonfinite numbers, invalid ranges, extra fields, and invalid course counts return HTTP 422 with field details.

The backend computes **GWA = sum(grade × units) / sum(units)** using decimal arithmetic. The example produces 7.75 weighted grade-units / 5 units = **1.55**, **Third Honor**, and **86.25%** on the visualization bar.

The response includes the entered courses and weighted contributions, course count, total units, total weighted grades, numeric `gwa`, two-decimal `gwa_display`, `classification`, `performance` (including Excellent and Just passing), `honor`, `is_passing`, `honor_eligible`, `failed_course_count`, and numeric `percentage` for a future bar.

| Unrounded GWA | Classification |
| --- | --- |
| 1.00 ≤ GWA ≤ 1.25 | First Honor |
| 1.25 < GWA ≤ 1.50 | Second Honor |
| 1.50 < GWA ≤ 1.75 | Third Honor |
| 1.75 < GWA ≤ 3.00 | Passing |
| 3.00 < GWA ≤ 5.00 | Failed |

**1.00 is excellent; 3.00 is just passing; 5.00 is failed.** Exact shared boundaries favor the higher honor. Classification uses the unrounded weighted average; displayed GWA and percentage round half up to two decimal places. For example, 1.250001 displays as 1.25 but receives Second Honor.

The bar uses **percentage = (5 − GWA) / 4 × 100**: 1.00 → 100%, 3.00 → 50%, 5.00 → 0%. This is a linear visualization, not an official school percentage conversion or a course completion percentage.

Honor labels and eligibility follow the supplied project bands only. A failed individual course is reported separately and does not override the average's label; institution-specific rules such as minimum course grades are not implemented. Calculations are returned immediately and are not stored.

## App 3: Pomodoro Timer

The default cycle follows the supplied example exactly:

```text
Study 25 → Short 5 → Study 25 → Short 5 → Study 25 → Short 5 → Study 25 → Long 15 → repeat
```

That means **four study sessions, three short breaks, and one long break**. The long break replaces the fourth short break. New intervals start automatically.

- **Start / Pause / Resume** control the current interval. **Reset timer** pauses and restarts that interval without awarding study credit or clearing task progress.
- Settings accept 0.01–180 minutes with up to two decimal places, allowing small timers. A running or partially paused interval keeps its remaining time when settings change; future intervals use the new settings. Reset applies the new duration now.
- Add a task title and a target of 1–99 pomodoros. Only completed study intervals count. Tasks can span multiple four-session cycles.
- At a task's target, a notification announces completion and the next task. The next task starts with the next study interval after the scheduled break; no confirmation is requested. When all tasks finish, the cycle continues as free study.
- A task added during an already-running free study interval begins with the next study interval, without retroactive credit. Reset a current task's study timer before removing that task.
- Timer state, task progress, and settings are saved under `queezo.pomodoro.v1` in local browser storage. They survive navigation and refresh in the same browser; they are not saved to the server or synced to other devices. Web Locks serialize updates across same-origin tabs where supported.
- Countdown uses an absolute deadline, rather than decrementing once per callback. If the browser sleeps or is closed, alerts may be delayed. On return, an expired interval is counted once and the next interval starts fresh; unattended overnight cycles are not credited.

Every interval change and task completion displays an in-app notification, including while using the other Queezo apps. **Enable desktop notifications** requests browser permission only when clicked. With permission, system alerts use a service worker when available, with a desktop Notification fallback. Clicking a notification opens the timer. A blocked/unsupported notification API keeps the in-app alerts active.

Keep the app open for timely notifications. This prototype does not provide closed-browser background alarms. Browser/OS notification permissions and notification display policies still apply. See the [browser notification documentation](https://developer.mozilla.org/en-US/docs/Web/API/Notifications_API) for platform behavior.

Run the timer's deterministic tests without waiting for real 25-minute intervals:

```powershell
node --test frontend/tests/pomodoro.test.mjs
```

## Persistence and tests

App 1 stores SQLite in the named `queezo_data` Docker volume. `docker compose down` keeps it; **`docker compose down -v` permanently removes it**. Keep the project name `queezo` to reuse its data. Timestamps are UTC. Writes acquire SQLite's write lock before checking mutable state, and foreign keys, review uniqueness constraints, and card-limit triggers protect persistence.

Run all backend tests in temporary test databases:

```powershell
docker compose run --rm --no-deps backend python -m pytest -q
docker compose config --quiet
```

For local development, run `python -m pytest -q` from `backend/`. See `VERIFICATION.md` for recorded validation and limitations. Public registration, password recovery, account deletion, Notes management, and GWA calculation history are not implemented.
