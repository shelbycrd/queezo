# Queezo project instructions

## Project overview

Queezo is a student workspace for two-sided flashcards, Classic and Multiple-Choice study, multiplayer Study Rooms, weighted GWA calculation, and Pomodoro. It also supports accounts, profiles, friendships, deck sharing, and an operator-only Admin Console.

- [frontend/src/](frontend/src/) contains Vue 3 views, Vue Router, components, and services. [frontend/js/](frontend/js/) contains shared browser utilities. Vite builds the frontend.
- [backend/app/](backend/app/) contains Python 3.12, FastAPI routers, Pydantic schemas, SQLAlchemy models, and services. [backend/app/gwa/](backend/app/gwa/) is a separate FastAPI service with stateless Decimal calculations. Pomodoro state lives in account-scoped browser storage.
- [compose.yaml](compose.yaml) and [nginx/](nginx/) define the Docker services, reverse proxy, and shared SQLite volume. Ollama is a separately configured inference service.
- Start with [AGENTS.md](AGENTS.md), the [README](README.md), and the [architecture index](docs/architecture/README.md). Use the [documentation index](docs/README.md) to find topic guides. Historical reports describe their original checkout. Verify details in code, especially [schema versions](backend/app/database.py) and [Admin Console behavior](docs/ADMIN_CONSOLE.md).

## Development environment

Use the [development guide](docs/DEVELOPMENT.md) for Compose, local Vite, and isolated test commands.

## Architecture guidelines

- Use Vue views, reusable components and lifecycle composables, and the shared [API client](frontend/js/api.js). Preserve same-origin routing, account-scoped state, error envelopes, and cleanup of requests, timers, and sockets.
- Use existing FastAPI dependencies, typed request schemas, and service boundaries. Recheck ownership, current visibility and share grants, and room membership or host authority for the resource in question. Keep the Admin Console server-local. [Authentication](docs/architecture/04-authentication-and-security.md)
- Keep Classic scheduling separate from Multiple-Choice. Preserve ordered progressive preparation, session snapshots, stable option IDs, and server grading. Reuse the persistent card-level distractor cache across solo and rooms. Preserve fingerprint and generation checks, leases, dependency invalidation, and same-deck fallback. String validation cannot establish semantic correctness. [Flashcards and AI](docs/architecture/05-flashcards-and-ai.md)
- Use authenticated WebSockets for viewer-specific snapshots and CSRF-protected HTTP for room writes. Keep clocks, eligibility, answer locking, reveal, and scoring server-authoritative. Preserve reconnect behavior. [Study Rooms](docs/architecture/06-multiplayer-study-rooms.md)
- Keep SQLite writes short and reuse the existing transaction helpers. Keep Argon2 and inference outside write transactions. Use additive, versioned migrations with verified pre-migration backups. Test upgrades on disposable copies. [Database recovery](docs/production/DATABASE_RELIABILITY.md)

## Coding standards

Prefer the smallest correct change. Reuse existing components and services, keep code readable, and use existing typing and validation conventions. Avoid new dependencies and rewrites unless required. Preserve the pastel-blue theme, accessibility, responsiveness, and unrelated features.

## Security and data protection

- Keep credentials, session and share tokens, and private user data out of logs, examples, and commits.
- Preserve authentication, CSRF, origin validation, and private-by-default deck access. Validate client input server-side and bind SQL parameters. Keep shell execution away from user input.
- Protect existing SQLite files and Docker volumes. Never reset, delete, or overwrite them. Avoid `docker compose down -v` and volume pruning. Use disposable databases, containers, and synthetic accounts for destructive or migration tests. Follow AGENTS.md for destructive or irreversible operations.

## Testing and verification

Run relevant tests in [backend/tests/](backend/tests/) and [frontend/tests/](frontend/tests/). Add focused regression coverage for confirmed bugs. For API changes, verify the frontend contract as well as the route. For study or room changes, exercise ordering, authorization, concurrency, reconnects, and timing where affected. Treat mocked and live Ollama checks separately. Report commands actually run, results, skipped checks, and unresolved issues.

## AI collaboration rules

Codex and Claude Code share this repository. Check Git status and read current files before editing. Another assistant’s work may be uncommitted. Preserve unrelated edits and coordinate overlapping changes. Use separate branches and worktrees for parallel development. Extend the existing implementation and update the relevant architecture chapter when behavior changes. Treat code as the authority for current behavior and AGENTS.md as the shared working rules. Surface instruction conflicts and preserve security and data protections while resolving them.

## Task execution

1. Identify the requested outcome and inspect affected code, docs, and dependencies.
2. Implement the smallest correct change while preserving other behavior and data.
3. Run scoped verification and summarize changed files, measured results, and remaining limitations.
