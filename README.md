# Queezo study apps

Two independently runnable FastAPI apps share this repository:

- **App 1 — Flashcards:** `app.main:app`, persistent decks, two-sided cards, and resumable recall practice.
- **App 2 — GWA Calculator:** `app.gwa.main:app`, a stateless weighted-average calculator. It uses the shared database for authentication, without storing calculation records. App 2 currently implements GWA rather than Notes management.
- **App 3 — Pomodoro Timer:** a browser-based timer and task queue at `/#pomodoro`. It runs locally in the frontend and stores its state in this browser, without a separate backend service.

The lightweight frontend prototype provides Home, two-sided Flashcards, a GWA Calculator connected to App 2, and a Pomodoro Timer. All UI files live in `frontend/`. A shared left sidebar and main page use the same rounded, soft blue theme, without coins, hearts, or a dashboard search bar. Open `http://localhost:8080` after starting Docker. GWA calculations and unfinished course entries are not saved across navigation or refresh; Pomodoro settings, task progress, and timer state are saved locally per account in the browser.

## Accounts and private data

Create an account at `http://localhost:8080/#signup`, or use the secure CLI in an interactive PowerShell terminal:

```powershell
docker compose exec backend python -m app.cli create-user
```

Enter a display name, unique username, unique email, and matching passwords with **more than 10 characters** (11 minimum). Display names may repeat. Usernames and emails are unique without regard to capitalization; usernames use 3–32 letters, numbers, or underscores. Each account receives a random unique UID. The signup page includes an optional red/yellow/green strength estimate; it recommends longer passwords and discourages predictable patterns without adding composition requirements. Signup signs you in automatically. CLI passwords stay hidden in the terminal. Sessions last seven days and survive refreshes and backend restarts; **Log out** revokes the current session immediately.

CLI commands include `list-users`, `show-user --uid UID`, `revoke-sessions --uid UID`, and `delete-user --uid UID`. Deletion requires repeating the exact UID and permanently removes that account's owned decks and history. See [AUTH_SETUP.md](AUTH_SETUP.md) for commands and migration details. Email verification and password recovery are not implemented.

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
- Signup / login / logout: `POST /api/auth/signup`, `POST /api/auth/login`, `POST /api/auth/logout`
- Restore current session: `GET /api/auth/me`

The first build needs internet to download images and Python dependencies.

The account menu is at the top right, with Profile, Help, and Log out. Profile shows your display name, username, UID, and email. Chat and notification buttons sit beside it. The chat drawer is a frontend-only local preview, with newest activity first; messages are not sent. Settings is at the bottom of the sidebar and includes a saved study-sound toggle for card page turns and Pomodoro play/pause. Primary action buttons use a raised press effect; secondary Open deck, Add course, and Clear controls stay flat. Navigation and other button clicks are silent.

### Try the frontend prototype

**Home** shows up to 20 public Community Decks in a horizontal carousel with previous/next arrows. The study streak counts days with a rated flashcard or a completed study Pomodoro, using Asia/Manila calendar days. The Friends container has Online and Offline tabs with empty states; friend connections and live presence are not implemented.

Choose **Flashcards** to search your decks by title. Use the separate **Create Deck** button to name and create a new deck. Portrait deck tiles show the title and card count. Enter a required question and answer directly in the deck editor; optional photos and typed bullet/numbered lists are rendered on both sides; formatting toolbar buttons are omitted. **Next Card** saves the card, plays a short page-turn sound, and clears the editor for another card. Saved cards appear below, and **Study deck** sits beside **Next Card**. Use the card order selector for most recent first or least recent first. Study opens a mode picker: Unlimited time, or Time bounded per question (seconds) or for the whole deck (minutes). Limit fields stay visible and editable with either choice; Unlimited does not apply a time limit. Question expiry reveals the answer for a manual rating; deck expiry ends the session. Timing is managed by the browser and survives a refresh in the same tab; it is a prototype rather than server-enforced timing. During study, **Enter** immediately reveals the answer below the question without flipping or animation. **1**, **2**, and **3** rate Hard, Normal, and Easy and advance; they also reveal first when needed. There are no multiple-choice answers.

Choose **GWA Calculator**, enter units and grades for at least one course, and select **What's my GWA?** Subject names are optional. Valid three-digit shorthand converts immediately: `175` → `1.75`, `225` → `2.25`, and `100` → `1.00`. Enter in a valid course row moves to the next course or adds one, up to 15. **Add course** and **Remove** keep the list between 1 and 15 courses. **Clear** starts a new calculation. The summary shows your GWA, classification, course count, total units, and a 0–100 grade-scale bar. The static honor-band guide is omitted. Editing inputs hides the previous summary until you recalculate.

Choose **Pomodoro** to use the large centered timer, with tasks beneath it. The Study, Short break, and Long break labels indicate the current phase; they are not buttons. Add tasks with a target number of study intervals, then press the central play icon. Timer settings default to 25 / 5 / 15 minutes and can be changed under **Timer settings**. The three controls are Reset timer on the left, play/pause in the middle, and Skip on the right. Running/Paused status labels are omitted. At each phase boundary the timer waits for play. Skip moves to the next phase without awarding study or task credit. Task completion still advances the task queue automatically.

After frontend-only source changes, rebuild with `docker compose up -d --build --no-deps --wait frontend`, then refresh the browser (Ctrl+F5 if it still shows the previous version). Backend/account changes require `docker compose up -d --build --wait`.

For independent development, install `backend/requirements.txt` in a Python 3.12 virtual environment, then run these commands in separate terminals from `backend/`:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python -m uvicorn app.gwa.main:app --host 127.0.0.1 --port 8001
```

Documentation is then at `http://localhost:8000/docs` and `http://localhost:8001/gwa/docs` respectively.

## App 1: Flashcards

All cards require a nonblank front and back, each at most 10,000 characters. `card_type` can be omitted and defaults to `two_sided`. If supplied, only `two_sided` is accepted. Creation and updates reject `one_sided`, null sides, and blank sides with HTTP 422. Partial updates keep omitted fields.

Optional `front_image` and `back_image` fields accept PNG, JPEG, or WebP base64 data URLs up to **1.5 MiB per image**. Omitted image fields are preserved during a partial update; explicit null removes an image. User text is rendered as text with a small bullet/numbered-list format, not arbitrary HTML. Study snapshots preserve photos alongside text, and answer photos remain hidden until reveal. Startup adds nullable photo columns to older databases without replacing existing rows.

Example body for `POST /api/decks/{deck_id}/cards`:

```json
{
  "front": "What does GWA stand for?",
  "back": "General Weighted Average"
}
```

Deck/card routes retain `/api/decks`, `/api/decks/{id}/cards`, and `/api/cards/{id}`. Decks hold at most 150 cards. Dashboard counts and the latest 50 sessions per deck remain available.

`GET /api/cards/recent?limit=12` returns the current account's newest cards (limit 1–30). `GET /api/dashboard/activity` returns the account's streak and active days in Asia/Manila. Rated flashcards mark a study day; the authenticated, CSRF-protected `POST /api/activity/pomodoro` marks a completed study interval without accepting client-provided dates. Streaks also include existing owned review history.

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

`POST /api/gwa/calculate` implements **What's my GWA?**. Send between **1 and 15 courses**:

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

The response includes the entered courses and weighted contributions, course count, total units, total weighted grades, numeric `gwa`, two-decimal `gwa_display`, `classification`, `performance` (including Excellent and Just passing), `honor`, `is_passing`, `honor_eligible`, `failed_course_count`, and numeric `percentage` for the visualization bar. The frontend keeps the summary compact; these API fields and classification rules are retained even though the static honor-band guide is not shown.

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

That means **four study sessions, three short breaks, and one long break**. The long break replaces the fourth short break. Each next interval waits for an explicit start using the timer’s main button.

- **Start / Pause / Resume** control the current interval. **Reset timer** pauses and restarts that interval without awarding study credit or clearing task progress.
- Settings accept 0.01–180 minutes with up to two decimal places, allowing small timers. A running or partially paused interval keeps its remaining time when settings change; future intervals use the new settings. Reset applies the new duration now.
- Add a task title and a target of 1–99 pomodoros. Only completed study intervals count. Tasks can span multiple four-session cycles.
- At a task's target, a notification announces completion and the next task. The next task starts with the next study interval after the scheduled break; task selection advances automatically, while every next phase waits for Start. When all tasks finish, free study remains available.
- A task added during an already-running free study interval begins with the next study interval, without retroactive credit. Reset a current task's study timer before removing that task.
- Timer state, task progress, and settings are saved in account-scoped local browser storage. They survive navigation and refresh in the same browser; they are not synced to other devices. A completed study interval also records a server-side study day for the Home streak, without uploading task titles or timer settings. Web Locks serialize updates across same-origin tabs where supported.
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

Run the frontend helper and timer tests with `node --test frontend/tests/*.test.mjs`.

## Deck visibility and Community Decks

New decks default to **Private**; all decks that existed before this feature remain Private. Choose visibility in Create Deck or save a change in the owner's deck workspace:

- **Private:** owner-only; shared access returns 404.
- **Public:** readable through Community Decks and its random share link.
- **Unlisted:** readable through its random share link, omitted from Community Decks.

These views require a signed-in account, consistently with the rest of Queezo. Only owners can edit/delete originals or access their study history. Shared views offer **Save private copy** and **Study a copy**; copies have new identities and belong to the reader. Switching the original to Private blocks future reads/copies through that link; previously saved copies remain independent.

Home's Community Decks carousel shows at most 20 public, assigned decks, newest-created first, with left/right scrolling. Sharing routes: `GET /api/community/decks`, `GET /api/shared/decks/{token}`, and CSRF-protected `POST /api/shared/decks/{token}/copy`. Owner deck responses now include visibility/share_token; shared responses omit owner IDs, card IDs, and study history. Deck PATCH accepts title and/or visibility, preserving omitted values.

Deck titles and question/answer text reject common URL forms in backend validation: HTTP(S), other schemes, bare domains/www, IP/local hosts, protocol-relative, encoded/Unicode and common defanged links. Photo data URLs are handled separately by the existing raster-image policy. Email/password inputs retain normal account validation. This is a conservative text-content rule, not a complete security scanner; images are not OCR-scanned for links. Existing text is preserved, but publishing/copying legacy decks checks for prohibited links before committing.

The sharing migration adds private-by-default visibility and random, unique share tokens without replacing old rows. A pre-upgrade database backup is kept privately in `/data/queezo-before-community-20261117.db` and ignored `outputs/backups/queezo-before-community-20261117.db`. Do not commit backups or actual share links for private material.

## Cloud visual theme — November 18, 2026

The current reference-inspired design uses a locally hosted Quicksand font, an original study-cloud mark, rounded white surfaces, a scalloped desktop sidebar, pill controls, and a restrained blue palette. The final visual layer is `frontend/css/cloud-theme.css`, loaded after the existing stylesheets. Its responsive rules cover the authenticated workspace, login/signup, deck editing/sharing, study/summary, GWA, Pomodoro, account pages, chat and notification panels. Asset provenance and font licensing are recorded in `frontend/assets/README.md`.

This changes presentation while retaining the current features, URL text restrictions, deck visibility, Community Decks, timing behavior, and account handling. Route navigation begins at the top of each page so the fixed controls do not cover content left at a previous page's scroll offset. Removed Quick Actions, dashboard search, sparkles, and footer captions remain absent.
