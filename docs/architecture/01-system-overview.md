# 01 · System overview

[Architecture index](README.md)

Queezo is a browser-based study companion. Students create decks, practice recall, calculate a weighted grade average, and manage timed focus sessions. Study Rooms let friends work through a single synchronized Multiple-Choice session. Three core study tools share one Vue interface.

| Actor | Capabilities and boundary |
| --- | --- |
| Visitor | Can browse discoverable profiles and open public or unlisted profiles. Shared-deck study and the workspace require sign-in. |
| Signed-in student | Owns decks and private study history, adjusts a profile, manages friend relationships, and can use permitted shared decks. |
| Room host | A room member who can configure, start, pause Collaborative review, return to the lobby, and administer the room through the room API. This permission is scoped to the room. |
| Room participant or spectator | Invited accounts can join. Active players can submit answers. Spectators can follow questions and chat, then participate after the lobby resets. |
| Operator | Uses the backend CLI for provisioning, revoking sessions, account deletion, legacy ownership, profile report review, and targeted cache clearing. Access relies on the deployment's operator controls. The user model has no administrator-role column. |

Sources: [frontend routes](../../frontend/src/main.js), [profile routes](../../backend/app/routers/profiles.py), [room routes](../../backend/app/routers/study_rooms.py), [operator CLI](../../backend/app/cli.py), [models](../../backend/app/models.py).

## Implemented subsystems

- **Flashcards.** An owned deck has two-sided cards and optional photos. Classic tests recall. Solo Multiple-Choice prepares questions progressively and can use a public or unlisted share link. Owners can publish, revoke sharing, or save an independent copy of someone else's shared deck.
- **Study Rooms.** Invite-only membership, room chat, automatic host handoff, Collaborative review, timed Challenge scoring, and live question snapshots.
- **Account and social.** Registration when enabled, email/password sign-in, profiles and privacy, profile search and reports, friend requests, presence, and study-room invitation notifications.
- **GWA.** A separate authenticated calculation API computes a weighted average for 1–15 courses and returns display rounding and classification. It does not save courses or grades.
- **Pomodoro.** The browser owns the timer and task queue. A completed study interval can mark the account's study day. Browser permission and platform support govern notifications.

Sources: [backend app](../../backend/app/main.py), [GWA app](../../backend/app/gwa/main.py), [Pomodoro service](../../frontend/src/services/pomodoro.js), [study activity endpoint](../../backend/app/routers/activity.py).

## Architecture style and stack

The shipped topology is a reverse-proxied Vue single-page application, a modular FastAPI backend, a calculation-only FastAPI GWA process, and shared file-backed SQLite. Nginx routes browser requests to the appropriate process. The application uses HTTP/JSON for requests and WebSocket snapshots for room and invitation state. There is no external identity provider, database server, or message broker in the configured stack.

Vue 3.5 and Vue Router provide the client runtime. Vite builds assets and runs the optional development server. Python 3.12, Uvicorn, FastAPI, Pydantic, SQLAlchemy, and SQLite provide the backend. The Docker image builds and checks SQLite 3.54.1. The project pins its Python packages and locks frontend package resolution. Ollama is an external HTTP service for cold Multiple-Choice generation, with `qwen3:1.7b` as the default model. The backup overlay can use Restic with an operator-configured repository. Browser Notifications, service workers, Web Audio, and localStorage are platform dependencies.

Sources: [frontend packages](../../frontend/package.json), [backend requirements](../../backend/requirements.txt), [backend image](../../backend/Dockerfile), [Compose](../../compose.yaml), [backup overlay](../../compose.backup.yaml), [Ollama guide](../OLLAMA.md).

See the [C4 context](diagrams/system-context.md), [C4 containers](diagrams/container-architecture.md), and [deployment details](07-deployment-and-infrastructure.md).
