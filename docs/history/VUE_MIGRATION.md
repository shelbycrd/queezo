# Vue frontend migration

Historical record. Use the [development guide](../DEVELOPMENT.md) for current commands and the [component guide](../architecture/02-architecture-and-components.md) for current routes.

The baseline is commit `4f82b9c` on the `vue` branch. The original frontend used hash links, page-local JavaScript, and Nginx serving files directly. Its 61 frontend tests passed before migration. The inventory below uses the checked-out branch as the source of truth.

## Run locally

Use Node.js 22.12 or newer for frontend development. The Docker build uses Node.js 24 and installs the versions in `frontend/package-lock.json`.

From the repository root, build and run the full stack:

```sh
docker compose up -d --build --wait
```

Nginx serves the Vite output at [localhost:8080](http://localhost:8080). The database and the API paths stay the same.

For Vite development, keep the Compose APIs running. Add the exact Vite browser origin, usually `http://localhost:5173`, to `AUTH_TRUSTED_ORIGINS` in the backend configuration and recreate the backend if you changed its environment. Keep any existing Compose origins in the list.

```sh
npm --prefix frontend ci
npm --prefix frontend run dev
npm --prefix frontend test
npm --prefix frontend run build
```

Vite proxies API and API documentation requests to the Compose gateway. Set `QUEEZO_PROXY_TARGET` when the gateway uses a different host or port. The production image copies only `dist/` into Nginx.

## Where the code lives

| Area | Vue implementation | Preserved behavior |
| --- | --- | --- |
| Navigation and shared UI | `src/main.js`, `src/App.vue`, `components/NoticePopup.vue`, `components/ButtonFeedback.js` | Account-aware navigation, back links, browser title, popups, button feedback, floating shapes, responsive layout |
| Accounts | `views/AuthView.vue`, `components/PasswordField.vue`, `services/session.js`, `views/AccountView.vue` | Cookie restoration, CSRF, login, signup, password visibility and strength, account details, logout, cross-tab checks, settings, Help |
| Friends and notifications | `components/FriendsDrawer.vue`, `views/FriendProfileView.vue`, `App.vue` | Search, presence, requests, accept and decline actions, drawer dismissal, friend profiles and public decks, timer notification panel |
| Decks and community | `views/DashboardView.vue`, `views/DecksView.vue`, `views/DeckView.vue`, `views/SharedView.vue`, `components/DeckTile.vue` | Streaks, carousel, visibility, search and sort, deck management, public and unlisted links, private copies, study a copy |
| Card editing | `views/DeckView.vue`, `components/EditorSide.vue`, `components/CardContent.vue`, `services/photos.js` | Two-sided drafts, bounded photos, list rendering, compact previews, pagination, search, shortcuts, save feedback |
| Classic study | `views/StudyView.vue`, `views/StudySummary.vue`, `components/StudyOptions.vue` | Reveal without flipping, ratings, shortcuts, timing, saved presentations, history and summary |
| Multiple-Choice | `views/MultipleChoiceView.vue`, `components/MultipleChoiceHistory.vue`, `js/multiple-choice-session.js` | Ordered preparation, polling, waiting, grading, history, refresh, retry, continue, cancellation, results, and timing |
| GWA | `views/GwaView.vue`, `js/gwa-input.js` | 1–15 courses, keyboard entry, shorthand conversion and editing, validation, weighted grade and result copy |
| Pomodoro | `views/PomodoroView.vue`, `services/pomodoro.js`, `js/pomodoro-core.js` | Timing, cycle, tasks, controls, account storage, cross-tab synchronization, in-app alerts and browser notifications |

`frontend/src` uses Vue's Composition API and shared reactive services. Pure helpers and API clients remain in `frontend/js`. View-scoped reads and listeners are released on unmount. Multiple-Choice polling uses the existing controller. Pomodoro runs independently of the active route so an interval can finish while another page is open. Original styles remain in `frontend/css`. Static assets, timer audio, and the worker now live in `frontend/public` and retain their public URLs.

The old DOM-rendered pages, navigation, account widgets, and modal bindings were removed. Nginx and Vite continue to use the existing backend contracts. No FastAPI, Ollama, cache, or SQLite changes are part of this migration.

## Compatibility and verification

- Vue Router emits `#/...` URLs. Existing `#...` links still resolve, including old share links.
- The baseline branch includes **Check answer** and its existing grading rules. Click-to-submit, study focus mode, feedback tones, and first-presentation retries from separate local work were absent from this branch baseline.
- Browser comparison checked geometry, background colors, and typography for eight deck-editor elements. The measurements matched between the original and migrated builds at the default desktop viewport and a 390 px mobile viewport.
- Browser workflows covered login, signup, logout, cookie restoration, deck creation, photo upload and edit, save via Ctrl+Enter, public deck copying, study of a copy, Classic reveal and rating, Multiple-Choice preparation and refresh, grading and history, GWA entry and calculation, Pomodoro controls and persistence, friend requests, notification panel, Settings, Help, and Escape dismissal.
- Automated regression checks passed for 65 frontend tests and 504 backend tests. The frontend checks now cover Vue view teardown, including aborting reads and removing global events, and shared state for notices and study options.
- The Vite development server served the Vue entry and proxied both API health routes. The production build compiled and ran through Nginx in a separate Compose project with a disposable database.
- The browser preview deliberately used unavailable Ollama with synthetic decks. It exercised the real backend's fallback path. Live model quality, actual operating-system notification delivery, and exhaustive pixel comparison across browsers were outside this verification.
