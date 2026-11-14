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

## Frontend redesign verification — November 14, 2026

- Final backend suite: **341 passed**, one third-party Starlette/AnyIO deprecation warning, in the isolated `queezo-ui-check` Docker project. The suite includes media validation, additive photo-column migration, ownership of recent cards and activity, hidden answer photos, snapshot preservation, and streak behavior, alongside the existing authentication, Flashcards, and GWA regressions.
- Final frontend suite: **38 passed** with `node --test frontend/tests/*.test.mjs`. This includes safe text/list rendering, image URL constraints, study shortcut mapping, immediate grade shorthand normalization, and existing authentication/Pomodoro coverage. All frontend JavaScript passed syntax checks.
- Browser checks in the isolated project verified a populated Home carousel that actually scrolls with its arrows, Online/Offline Friends empty states, portrait deck tiles, and a PNG photo selected and previewed in the inline card editor. List formatting was also exercised.
- The redesigned screens share the sidebar and main-page layout. All UI files are in `frontend/`; backend changes support card photos and account-private study days. Nginx accepts the two permitted image payloads within its 5 MiB request limit.
- Before upgrading the saved database, SQLite's backup API created `/data/queezo-before-ui-20261114.db`. The pre-upgrade inventory was **1 user, 3 decks, 11 cards, 5 study sessions, and 69 reviews**. The isolated preview uses its own data volume and disposable account.

Friends tabs are presentation placeholders with honest empty states; connections and live online presence are not implemented. The generated page-turn sound is implemented, but speaker output has not been verified. Native OS notifications remain subject to the previously recorded browser/OS limitations.

Final browser and deployment checks:

- Saved a question with a PNG photo and a bulleted answer. Next Card saved the card, reset the composer, and displayed both sides in the saved-card list. Study beside it opened the saved deck with an empty draft.
- Enter revealed the answer below the still-visible question. The card's computed transform and animation were both `none`. Keys 1 and 2 rated unrevealed cards and advanced; key 3 worked both after Enter and directly from an unrevealed card. A one-card session completed after two Easy ratings.
- Typed `175`, `225`, and `100` character by character: the grade fields immediately became `1.75`, `2.25`, and `1.00`. Enter added the next course and focused its subject. Three units at 1.75 plus two at 2.25 returned **1.95**, Passing, and **76.25%**. A single 1.00 returned **1.00** and **100%**. No static honor-band guide was present.
- A six-second study timer automatically entered its short break, displayed an in-app completion alert, and credited exactly one pomodoro to its task. The dashboard displayed the recorded study day and a one-day streak. Restored 25 / 5 / 15 minute durations and paused the preview timer. Desktop notification permission was left unchanged.
- Verified Home, deck tiles, GWA, and Pomodoro at a 390px viewport with no document overflow; checked Home at 820px and the desktop layout at 1280px. Narrow deck tiles remained portrait-shaped. Timer and task bounding boxes confirmed tasks below the timer. Reset temporary viewport overrides afterwards.
- Upgraded the actual `queezo` stack at `http://localhost:8080` with `docker compose up -d --build --wait`. All three services are healthy and `nginx -t` passed. SQLite integrity is `ok`; post-upgrade counts match the backup exactly: **1 user, 3 decks, 11 cards, 5 study sessions, and 69 reviews**. The nullable photo columns were added successfully.
- Saved redesign previews under `outputs/`: `queezo-home-redesign.jpg`, `queezo-decks-redesign.jpg`, `queezo-study-redesign.jpg`, `queezo-gwa-redesign.jpg`, and `queezo-pomodoro-redesign.jpg`. Populated previews use disposable data from the isolated project, not the user's saved account.
- The preview console reported no warnings or errors. Confirmed the upgraded app's themed login page at `http://localhost:8080`. Copied the pre-upgrade backup to the ignored `outputs/backups/queezo-before-ui-20261114.db`.
- Removed only the isolated `queezo-ui-check` containers, network, and disposable volume after verifying its Compose project label. The main `queezo` stack and saved volume remain running.

## Frontend refinements — November 14, 2026

- Removed sparkle decorations and the requested Home, Flashcards, GWA, and Pomodoro captions. Home now lists latest decks sorted newest first.
- Deck search filters titles without creating data; Search and Create Deck are separate controls. Browser QA covered matching/no-match searches and creating a deck through the separate dialog in an isolated preview.
- Study, Short break, and Long break are clickable timer modes. Selecting another mode loads its full duration and waits for Start; unfinished study intervals receive no credit. Browser QA verified 25/5/15 mode selection, running a selected break, refresh persistence, and unchanged task progress after switching.
- All 40 frontend tests passed, including manual mode persistence, no false study credit, and cycle continuation. Changed JavaScript syntax checks and git diff whitespace checks passed.
- Rebuilt only the main frontend with its existing backend and saved volume retained; the frontend is healthy at http://localhost:8080. Removed the isolated preview after verifying its volume label. Preview: outputs/queezo-deck-search.jpg.

## Soft blue theme and account menu — November 14, 2026

- Recolored purple surfaces and accents to soft blue, including login, cards, calculator, timer, and icons. Most action buttons now have raised edges, a short press movement, and a synthesized gentle click sound. Semantic Hard/Normal/Easy colors remain readable. Reduced-motion preferences suppress press movement.
- The account name/menu is at the top right. Profile shows the current account, Help provides app instructions, and Log out uses the existing revocation flow. Settings is at the bottom of the desktop sidebar (bottom right on phones), with a persistent sound toggle covering clicks and page turns. The displayed account name is the email local part because accounts currently have no separate name field.
- GWA uses compact single-line rows with shared column headings and accessible per-input labels. Browser QA entered five courses and calculated 1.75 from 15 units. On a 390px phone viewport the rows were 46px tall and the fifth ended at 576px; document width stayed within the viewport. Desktop and phone layouts were visually inspected.
- Pomodoro mode labels are non-interactive phase indicators again. Confirmed their DOM elements are spans with no button role or mode-switch listener.
- Browser QA checked Profile, Help, persisted sound-off after refresh, re-enabling sound, dropdown navigation, and successful logout. The preview console reported no warnings or errors. Speaker output was not independently verified.
- All 40 frontend tests passed; changed modules passed node syntax checks and git diff whitespace checks. Rebuilt only the main frontend; it is healthy at http://localhost:8080. Backend services and saved data were retained. Isolated preview resources were removed after verifying the volume label.
- Saved outputs/queezo-blue-home.jpg and outputs/queezo-blue-gwa.jpg using disposable preview data. Temporary viewport overrides were reset.

## Deck polish, study options, and local chat — November 14, 2026

- Removed the four requested captions and all generic click/navigation sound handlers. Kept the existing optional card page-turn sound. Open deck, Add course, and Clear have no raised shadow or press transform; browser computed styles confirmed all three shadows are none.
- Your Decks and Home share the same portrait deck component. Pastels are shuffled without repeats until the palette is used, with a stable color per deck during navigation. Card editing retains photos, removes list toolbar buttons, and offers most/least recent sorting. Browser QA confirmed Question 3/2/1 became Question 1/2/3.
- Added back links for subpages and an exit/back control during study. Study now opens a two-choice dialog: Unlimited time or Time bounded, with per-question seconds or entire-deck minutes inside the timed choice.
- Browser QA verified a two-second question timer revealed the answer without assigning a rating; rating advanced to a new question and refresh preserved its deadline. A one-minute whole-deck timer ended the session after 1m 0s with zero fabricated reviews and showed the time-limit summary. Unlimited sessions have no countdown. These are browser-managed prototype limits, not server-enforced deadlines.
- Added notification/chat icons beside the profile. Notifications show available timer updates or an empty state. The profile popover and chat drawer use 0.2s animations, confirmed through computed styles; reduced-motion preferences are honored.
- Chat remains frontend-only. Disposable local conversations and messages were created in the preview; no chat network service exists and no messages are sent. New activity reordered Project group/Biology group to Biology group/Project group, and the order survived refresh. Data is scoped per account in this tab session. Logout clears visible panels.
- Desktop and 390px phone checks covered modal fit, drawer width, navigation, notifications, and logout. No document overflow or preview console warnings/errors were observed. Saved outputs/queezo-study-options.jpg, outputs/queezo-pastel-decks.jpg, and outputs/queezo-chat-preview.jpg using disposable data. Temporary viewport overrides were reset.
- All 43 frontend tests passed, including bounded-time validation/account isolation and recent-chat ordering. Changed modules passed syntax checks and git diff whitespace checks. Rebuilt only the main frontend and verified the updated login at http://localhost:8080. Backend code/services and saved data were retained. Removed the isolated preview after checking its volume label.

## Navigation placement — November 14, 2026

- Back navigation uses a circular white button with a dark SVG chevron. It appears only on deck, study, and study-summary subpages. Your Decks, GWA, Pomodoro, and other main pages have no back button. Desktop back positioning is 22px from the top; mobile aligns it beside the deck heading.
- Raised normal page content by reducing desktop top padding from 100px to 72px and mobile from 26px to 18px. Removed duplicate deck breadcrumbs and the YOUR SPACE navigation caption.
- Chat and notification controls have circular borders, white backgrounds, and no raised shadow. Notifications are a non-modal dropdown, so the same bell can close it; outside click and Escape also close it. Expanded state is exposed to assistive technology.
- Browser QA confirmed open/close using the bell, outside-click and Escape dismissal, absent back buttons on all three main app pages, and navigation from a deck back to Your Decks. Computed button borders were circular with no shadow. A 390px phone viewport had no document overflow; temporary viewport overrides were reset. The console reported no warnings or errors.
- All 43 frontend tests passed, changed modules passed syntax checks, and git diff whitespace checks passed. Rebuilt only the main frontend, which is healthy at http://localhost:8080. Saved data/backend services were retained. Removed the disposable preview after verifying its volume label. Screenshot: outputs/queezo-navigation-refinement.jpg.

## Pomodoro phase confirmation — November 14, 2026

- Completed intervals now prepare the next phase with a full duration, no active deadline, and an awaiting-start flag. The main timer button becomes Start short break, Start long break, or Start study. Clicking it starts that phase and restores Pause/Resume. No confirmation modal is used.
- Completed study credit, task advancement, and completion notifications are retained. Waiting and browser refresh cannot produce additional credit. The waiting state persists per account and older saved timer states remain compatible. Settings updates preserve the pending prompt; reset returns the current phase to a normal fresh Start state.
- Guarded the expiry/click boundary so a Pause/Resume click that discovers a completed interval cannot also start the next phase. Completion notices are now positioned clear of account controls, with working dismissal.
- All 45 frontend tests passed, including indefinite waiting after study/short/long phases, refresh restoration, explicit start, pause/resume, settings/reset behavior, legacy saves, repeated cycles, task credit, and account isolation. Changed modules passed syntax checks and git diff whitespace checks passed.
- Browser QA used three-second intervals to verify all three next-phase prompts, unchanged waiting time after refresh, Pause/Resume after starting, the long break after four studies, and return to a waiting study phase. Restored default 25/5/15 durations and left the disposable preview stopped. A 390px viewport had no document overflow; its temporary override was reset. The console had no warnings/errors. Screenshot: outputs/queezo-pomodoro-next-phase.jpg.
- Rebuilt only the main frontend at http://localhost:8080; it is healthy. Existing backend services and saved data were retained.
- Removed the isolated preview after checking its volume label; the main app remains running.
