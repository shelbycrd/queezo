# Architecture verification

[Architecture index](README.md) · [Decisions and known limits](09-architecture-decisions.md)

## Source baseline

Reviewed November 24, 2026 against commit `2e2b636`. The checkout was clean before the documentation work. Application, schema, Docker configuration, and student data were outside the change set.

| Area | Evidence checked |
| --- | --- |
| Frontend | Vue bootstrap and router guards, application shell, owner and shared deck views, Classic and Multiple-Choice views, room and invitation components, session wrapper, calculator and Pomodoro modules. [Frontend source](../../frontend/src/), [browser utilities](../../frontend/js/) |
| Backend | Mounted routers and methods, middleware, authorization dependencies, worker lifespan, error envelopes, GWA app and CLI. [Main app](../../backend/app/main.py), [routers](../../backend/app/routers/), [auth](../../backend/app/auth/), [GWA](../../backend/app/gwa/), [CLI](../../backend/app/cli.py) |
| Database | Compared all 24 physical tables with ORM declarations and the PK/FK catalog emitted by a freshly initialized disposable SQLite 3.54.1 database. Confirmed schema version 3, 14 installed triggers, and zero `PRAGMA foreign_key_check` violations. [Schema source](../../backend/app/database.py), [ORM classes](../../backend/app/models.py), [table catalog](03-database-design.md) |
| Inference and solo study | Compared JSON-mode request, bounded attempts, validation, leases, fallback dependencies, invalidation, immutable snapshots, shared-access checks, ordered readiness, and grading with both cache consumers. [Generator](../../backend/app/services/distractors.py), [cache](../../backend/app/services/distractor_cache.py), [solo worker](../../backend/app/services/multiple_choice.py), [room worker](../../backend/app/services/room_study.py) |
| Multiplayer | Traced invitation issuance and acceptance, ready/start, scope of snapshots before reveal, round progression, scoring, socket connection lifecycle, and host departure. [Room routes and sockets](../../backend/app/routers/study_rooms.py), [room rules](../../backend/app/services/study_rooms.py), [round engine](../../backend/app/services/room_study.py) |
| Infrastructure | Inspected base and overlay service definitions, image commands, proxy locations and forwarded headers, runtime defaults, and backup/restore procedures. [Base Compose](../../compose.yaml), [development](../../compose.dev.yaml), [backup](../../compose.backup.yaml), [Nginx](../../nginx/nginx.conf) |

## Tests

| Check | Result and scope |
| --- | --- |
| Focused backend tests | **257 passed, 1 skipped** in an isolated Docker invocation with disposable SQLite and the checkout's source. The skipped case requires live Ollama. Starlette emitted one TestClient deprecation warning. |
| Frontend suite | **74 passed** with `npm test` from `frontend/`. These are frontend unit tests, not a manual browser walkthrough. |

The backend run included `test_auth.py`, `test_sharing.py`, `test_study.py`, `test_gwa.py`, `test_study_rooms.py`, `test_distractor_cache.py`, `test_multiple_choice.py`, and `test_phase2_reliability.py`. See the [test sources](../../backend/tests/).

## Diagram checks

| View | Mermaid | PlantUML |
| --- | ---: | ---: |
| System context and containers | 2 | 0 |
| Components | 0 | 2 |
| Domain classes | 3 | 0 |
| Physical ER | 3 | 0 |
| Sequence | 13 | 0 |
| State machine | 5 | 0 |
| Activity | 0 | 6 |
| Deployment | 0 | 2 |
| **Total** | **26** | **10** |

Rendered all 26 Mermaid sources with Mermaid CLI 11.12.0 and all 10 PlantUML sources with PlantUML 1.2025.4. The PlantUML SVG files are checked in as previews. Mermaid SVGs were generated in a temporary folder.

Validated the base, development, and backup Compose configurations with `docker compose config --quiet`. Verified relative Markdown links, heading references, diagram counts, and the ER table inventory. This checkout contains no tracked GitHub Actions workflows.

## Verification limits

- The live model variant, timing benchmarks, and semantic quality review were outside this verification run. Prior observations are linked in [Flashcards and AI](05-flashcards-and-ai.md).
- Public TLS, browser behavior behind an external gateway, production load, off-host Restic credentials, and a real disaster-recovery exercise require deployment-specific access. The [infrastructure chapter](07-deployment-and-infrastructure.md) distinguishes configured local topology from production requirements.
- Class and ER diagrams are physical-model views with selective non-key attributes. The [table catalog](03-database-design.md) adds constraints, indexes, migration behavior, and ownership information. Job and round state diagrams show selected transitions derived from code.
- Original framework-selection rationale is undocumented. Inferences are marked in [Architecture decisions](09-architecture-decisions.md).
