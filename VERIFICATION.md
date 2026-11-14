# Backend verification — November 12, 2026

## Executed successfully

- `docker compose config --quiet` validated the three-service configuration.
- Docker images built successfully for the Flashcards API, GWA Calculator API, and Nginx gateway.
- An isolated Compose project, `queezo-backend-check`, started all three services on port 18080 with healthy status. It used its own temporary SQLite volume, not the saved `queezo` database.
- The final backend suite passed in Docker: **253 tests passed**. One dependency deprecation warning comes from Starlette's reference to AnyIO's older BlockingPortal alias.

The suite was run with:

```powershell
docker compose -p queezo-backend-check run --rm --no-deps backend python -m pytest -q
```

## Coverage

- Two-sided-only card creation and partial updates, required front/back content, rejection of the removed type, and direct database enforcement.
- Legacy database detection, explicit conversion of cards and historical snapshots, atomic rollback on invalid/incomplete answer mappings, and repeatable installation of database guards.
- Existing CRUD, 150-card cap, concurrent last-slot requests, cascade deletion, persistence, reveal gating, duplicate/stale/concurrent ratings, snapshots, study completion, summaries, and fresh sessions.
- Seeded scheduling across 30 seeds and deck sizes 1, 2, 3, 10, and 150.
- GWA weighted arithmetic, fractional units, optional subjects, 1- and 15-course limits, invalid inputs, exact honor/pass boundaries, rounding, percentage endpoints, performance labels, and failed individual course counts.
- Separate routes and OpenAPI contracts for the two independently runnable apps.

## HTTP integration checks

Requests through the actual Nginx gateway verified:

- Both API health endpoints and interactive documentation routes.
- Final-image GWA response at 1.00 returning First Honor, Excellent, and 100%; `nginx -t` passed.
- A weighted GWA of 1.55 from 3 units at 1.25 and 2 units at 2.00, returning Third Honor and 86.25%.
- Invalid empty course lists returning HTTP 422.
- Rejection of one-sided cards, acceptance of mandatory question/answer cards, answer concealment, rejection of premature ratings, reveal, and a completed two-review session.
- Removal of the temporary test deck after the checks.

## Limits

The backend validation above predates the frontend prototype. The frontend checks below were completed afterwards; GWA draft persistence and a production frontend are outside this prototype's scope.

The native Windows test attempt was stopped after its event loop blocked on a sandbox-restricted socket operation. The full Docker run above is the completed test result.

No conversion was applied to the user's saved database. Legacy conversion was tested on temporary databases. The default `queezo` deployment was not replaced by the isolated test stack.

After verification, the isolated test containers, network, and volume were removed. The volume's Compose project label was checked before cleanup.

## Frontend prototype verification

- All seven frontend JavaScript modules passed `node --check`.
- Rebuilt the local frontend image and restarted it successfully with healthy status at `http://localhost:8080`. The existing backend services and saved volume were retained.
- Browser checks verified the Apps chooser and navigation to Flashcards and GWA Calculator.
- GWA: 3 units at 1.25 and 2 units at 2.00 displayed **1.55**, **Third Honor**, **5 total units**, and **86.25%**.
- Course rows retained entered values while adding/removing. At 15 courses Add was disabled; removing a course enabled it again. Clear restored one empty course with Remove disabled.
- Zero units were blocked by browser validation. Editing rows hid the outdated summary.
- Single-course grades 1, 3, and 5 displayed Excellent / 100%, Just passing / 50%, and Failed / 0%, respectively.
- Flashcards: no card-type selector was present; a question without an answer was blocked. Saved both sides, revealed the answer, rated Easy twice, and reached the completed session summary.
- The temporary verification deck was removed through the API after checking its exact ID and title. Existing user decks were retained.
- Verified desktop layout at 1280px and the default narrow preview at 304px, with no horizontal document overflow. The temporary viewport override was reset. The preview console reported no errors.
- Saved previews: `outputs/queezo-apps-preview.jpg` and `outputs/queezo-gwa-preview.jpg`.

The local `queezo` app is left running with the updated prototype. GWA calculations are performed by App 2; the frontend does not duplicate its grading logic.

## App 3: Pomodoro verification

- **23 deterministic timer tests passed** with `node --test frontend/tests/pomodoro.test.mjs`.
- Coverage includes the exact 25/5/25/5/25/5/25/15 sequence across repeated cycles, custom decimal durations, pause/resume, deadline-based remaining time, reset without false credit, active task binding, automatic task advancement, duplicate completion protection, task targets spanning cycles, saved-state recovery, invalid inputs, and late browser wake-up handling.
- All nine frontend modules and `pomodoro-worker.js` passed JavaScript syntax checks.
- Rebuilt only the frontend image and restarted its service successfully with healthy status. Existing backend services and their data volume were retained.
- Browser checks used 6-second study, 3-second short, and 9-second long intervals. Observed four study completions followed by a long break, then repetition. Two example tasks each reached exactly 2/2 and completed automatically; free study continued afterwards.
- In-app interval and task-completion notifications appeared without confirmation. Timer and task updates continued while viewing the Apps page. Pause, refresh recovery, and saved settings/progress across app navigation were verified.
- Restored the 25 / 5 / 15 minute defaults and left the timer stopped at a fresh Study interval. Example task progress remains only in the preview browser's local storage.
- Checked the App 3 link/card and navigation to the existing Flashcards and GWA views. All three app cards were present.
- Verified layouts at the default 304px preview width and a 1280px desktop width without horizontal overflow. Restored the default viewport afterwards. The browser console reported no errors.
- Saved `outputs/queezo-pomodoro-preview.jpg` as a visual record.

Desktop notification permission was left unchanged. Native OS toast delivery and notification clicks were not exercised; the permission control and worker integration are implemented, with in-app fallback. No browser-closed or sleep-time alarms are promised: this is a browser-local prototype that requires the page to be open for timely delivery. Cross-tab serialization uses Web Locks when available; multi-tab race behavior was not separately exercised in browser QA.

## Authentication verification — November 13, 2026

- Final backend suite: **324 passed**, one third-party Starlette/AnyIO deprecation warning, in Docker. This includes the original Flashcards/GWA regressions plus authentication, SQL ownership, CLI, migration, and rate-limit cleanup tests.
- Final frontend suite: **30 passed** with `node --test frontend/tests/*.test.mjs`, including stale-account response rejection, CSRF headers, per-account Pomodoro storage, and a notification finishing after logout.
- All frontend modules and the notification worker passed syntax checks. Docker builds, Compose configuration, health checks, and `nginx -t` passed.
- Actual interactive `docker compose ... exec backend python -m app.cli create-user` was exercised in the isolated `queezo-auth-check` stack. Password and confirmation prompts did not echo the entered secret.
- Real HTTP checks through Nginx verified login, seven-day cookie lifetime, HttpOnly/SameSite attributes, CSRF and hostile-origin rejection, a full Flashcards study session, and GWA calculation. Cookies remained valid across a real backend restart, then became unusable after logout, including replay of the old cookie.
- Browser checks verified generic incorrect-credential feedback, correct login/dashboard redirect, refresh restoration, authenticated GWA calculation, expired-session redirect/message, logout, and prevention of logged-out navigation to decks.
- Expiration boundary tests use controlled database timestamps; testing did not wait seven calendar days. Production Secure/host-only cookies and rejection of insecure production configuration were verified in HTTPS TestClient requests; no public HTTPS deployment or certificates were configured.

The live app was upgraded with `docker compose up -d --build --wait`. All services are healthy. Anonymous requests to `/api/auth/me`, `/api/decks`, and `/api/gwa/calculate` return HTTP 401. The HTML gateway returns frame-protection/CSP headers.

Before migration, SQLite's backup API saved `/data/queezo-before-auth-20261113.db`, also copied to `outputs/backups/queezo-before-auth-20261113.db`. After migration, live counts were unchanged: **2 decks, 8 cards, 2 study sessions, and 43 reviews**. Owners remain NULL. No real account was created and no legacy data was assigned automatically.

The isolated verification stack, disposable accounts, and temporary database volume were removed after checking the volume's Compose project label. The real `queezo` volume and its backup were retained. The running frontend displays the login page; create the first real account using the CLI documented in `AUTH_SETUP.md`.

See `AUTH_IMPLEMENTATION.md` for the changed-file inventory, implementation details, and remaining operational setup. Login preview: `outputs/queezo-login-preview.jpg`.
