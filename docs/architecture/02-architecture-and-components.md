# 02 · Architecture and components

[Architecture index](README.md) · [Component diagram](diagrams/components.md)

## Vue application

`frontend/src/main.js` creates Vue and Vue Router, restores account state before mounting, installs guards and shared styles, and lazy-loads route views. Most routes use hash navigation. Clean `/u/:username` profile entries use history routing, with Nginx's SPA fallback serving the entry page. Views compose feature components and own their local state. `App.vue` provides navigation, shell-level messages, the study dialog, account controls, the room invitation subscriber, and the Pomodoro clock. The router's view scope is keyed by account and route path so old view state is torn down at navigation.

| Area | Component or module |
| --- | --- |
| Account, profile, and social | `AuthView`, `ProfileView`, `PeopleView`, `ProfileSettings`, `FriendsDrawer`, `RoomInvitations` |
| Deck workflows | `DecksView`, `DeckView`, `SharedView`, `DeckTile`, `EditorSide`, and `CardContent` |
| Study | `StudyOptions`, `StudyView`, `SharedStudyView`, `MultipleChoiceView`, `PreviousSession`, and `multiple-choice-session.js` |
| Multiplayer | `RoomView`, `RoomLobbyAvatars`, `RoomFriends`, `RoomChat`, and `services/rooms.js` |
| Tools | `GwaView` and `gwa-input.js` for calculation input, `PomodoroView` and `pomodoro.js` for focus sessions |

State is held in Vue refs, component state, and small shared modules. Authentication state and the CSRF value are memory-only, with the browser cookie maintaining the authenticated session. Pomodoro data and selected preferences use browser storage. `api.js` centralizes same-origin fetches, CSRF headers, no-store requests, account-version checks, and error conversion. `lifecycle.js` aborts scoped reads and removes event listeners.

Sources: [entry and guards](../../frontend/src/main.js), [shell](../../frontend/src/App.vue), [state](../../frontend/src/services/session.js), [API client](../../frontend/js/api.js), [lifecycle composables](../../frontend/src/composables/lifecycle.js), [views](../../frontend/src/views/), [components](../../frontend/src/components/).

## Backend modules

| API area | Entry and responsibility |
| --- | --- |
| `/api/auth` | `auth/router.py` handles sign-up, login, account snapshot, password change, and logout. `auth/service.py` owns credential and session helpers. |
| `/api/decks`, `/api/cards`, `/api/dashboard` | `routers/decks.py` handles owner-scoped CRUD, media limits, and Classic history. `routers/community.py` serves public deck metadata and shared-deck read/copy. The share-token lookup sits in `services/ownership.py`. |
| `/api/study` | `routers/study.py` validates the current presentation and records Classic reviews. `services/study_scheduler.py` selects cards. `presenters.py` serializes snapshots and summaries. |
| `/api/multiple-choice` | `routers/multiple_choice.py` starts owned or shared solo sessions and exposes status, start, retry, continue, question, answer, and cancel. `services/multiple_choice.py` owns the coordinator, ordered preparation, and grading. |
| `/api/rooms` | `routers/study_rooms.py` provides room REST actions and two WebSocket endpoints. `services/study_rooms.py` handles membership and lobby operations. `services/room_study.py` owns preparation, the clock loop, scoring, and snapshots. |
| `/api/profiles` and `/api/friends` | `routers/profiles.py` handles lookup, discovery, self-editing, and reports. `routers/friends.py` handles requests and session presence. Report review is in the CLI. |
| `/api/dashboard/activity` and `/api/activity/pomodoro` | `routers/activity.py` and `services/activity.py` record one study-day row per account and Manila calendar day and calculate streaks. |
| `/api/gwa/*` | `gwa/main.py` is its own ASGI entry. `gwa/schemas.py` validates decimals and course data. `gwa/service.py` is a pure calculation module. |

Both apps import the authentication dependency, shared model definitions, and database utilities. GWA validates the account in SQLite and computes its response locally. It does not make HTTP calls to the Flashcards backend. SQLAlchemy session dependencies control read and write scope. Pydantic schemas apply transport-level validation. Some domain rules live directly in routers, and some are centralized in service modules and database constraints.

Sources: [router registration and lifespan](../../backend/app/main.py), [GWA entry](../../backend/app/gwa/main.py), [routers](../../backend/app/routers/), [services](../../backend/app/services/), [shared schemas](../../backend/app/schemas.py), [dependencies](../../backend/app/auth/dependencies.py).

## Profiles, friendships, and notifications

Profile views separate public payloads from owner-only fields. The owner API supports a 128-character bio, up to five distinct known interests, avatar choice, visibility, and an eligible public featured deck. Display name changes are limited to once in 14 days, and avatar changes to ten per hour. Public deck listings on a profile support title filtering, ordering, and paginated card counts. The profile report API stores authenticated reports under per-target and per-reporter limits, with CLI review. [Profiles API](../../backend/app/routers/profiles.py), [allowed interests](../../backend/app/interests.txt), [operator CLI](../../backend/app/cli.py)

Friendship stores one canonical user pair and the requester's identity. A pending pair is visible to the requester and recipient, and acceptance enables friendship actions and presence. A user is online when an unexpired session has a heartbeat newer than two minutes. This social presence clock is separate from room connection presence. Room notifications project invitation state from SQLite and wake the recipient's browser through a dedicated WebSocket, with REST recovery. [Friendship API](../../backend/app/routers/friends.py), [presence predicate](../../backend/app/services/presence.py), [invitation component](../../frontend/src/components/RoomInvitations.vue)

## Calculator and timer

The GWA endpoint accepts one to fifteen courses with optional subject, positive units, and grades from 1 to 5. It divides the sum of weighted grades by total units using Decimal arithmetic. The result includes two-place display rounding, classification based on the unrounded value, and a linear 0–100 percentage. The UI owns input formatting and the calculation lifecycle. The API does not persist course entries. [Calculator inputs](../../backend/app/gwa/schemas.py), [math](../../backend/app/gwa/service.py), [calculator view](../../frontend/src/views/GwaView.vue)

Pomodoro uses a local deadline and an explicit Start for the next phase. Defaults are 25 minutes of study, five for a short break, and fifteen for a long break. A cycle has four completed study intervals before a long break. The timer can credit a completed interval to the active task and notify the learner at phase changes. The service stores tasks and settings under the account's browser key, coordinates tabs when Web Locks are available, and can record the study day through the authenticated activity API. [Timer state machine](../../frontend/js/pomodoro-core.js), [browser service](../../frontend/src/services/pomodoro.js), [notification worker](../../frontend/public/pomodoro-worker.js), [activity endpoint](../../backend/app/routers/activity.py)

## Runtime coordination and failures

The main API initializes SQLite, settles interrupted solo jobs, and starts `PreparationJobs` plus `RoomEngine`. Solo jobs use in-process tasks with durable session records. The room engine has preparation and round/cleanup loops. Both engines share an async model lock, while card leases coordinate writers through SQLite. Authentication uses a separate four-slot semaphore and runs password operations in worker threads. Inference and expensive password operations happen outside write transactions.

The main API wraps HTTP and validation errors in `error.message` with optional field details, maps integrity conflicts to 409 and database operational failures to 503, and keeps raw validation inputs out of public responses. GWA defines its own FastAPI app and validation handler. The Vue API client accepts this envelope and falls back to a status message on other shapes. Socket rejection, connection limits, and recovery are documented in [Study Rooms](06-multiplayer-study-rooms.md).

Sources: [API error handlers](../../backend/app/main.py), [validation error formatting](../../backend/app/errors.py), [request middleware](../../backend/app/auth/middleware.py), [MC coordinator](../../backend/app/services/multiple_choice.py), [room engine](../../backend/app/services/room_study.py), [auth admission](../../backend/app/auth/router.py).
