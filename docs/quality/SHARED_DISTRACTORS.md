# Shared distractor verification

Solo owned-deck study, signed-in practice from a share link, and Multiplayer use the same row per original flashcard ID. The cache stores three text values in a SQLite JSON array and keeps existing validation, adaptive retries, render-order shuffling, and server-side grading. Saved questions retain their option IDs and grading snapshots. Shared solo sessions support refresh and retry for their 24-hour lifetime and stay out of Previous Session and study streaks.

Schema v3 adds `flashcard_distractor_jobs`, a source flag on the existing cache, and a hashed share grant on solo sessions. Startup takes the existing verified pre-migration backup before upgrading a populated database. The v2 regression checks exact cache text, fallback backfill, nullable session metadata, and foreign keys. All workloads below used disposable databases.

## Four-card measurements

| Synthetic scenario | Cold preparation | Warm other mode | Warm second-user solo | Cold Ollama HTTP | Warm Ollama HTTP | Fallback entries |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| Local Ollama online, solo → room | 13.508 s | 0.392 s | 0.201 s | 4 completed requests | 0 | 0 |
| Ollama unreachable, solo → room | 0.405 s | 0.387 s | 0.233 s | 4 connection attempts, 0 delivered | 0 | 4 |
| Mocked AI success, solo → room | 0.346 s | 0.781 s | 0.071 s | 0 network requests, 4 mocked generation calls | 0 | 0 |
| Mocked outage, room → solo | 0.672 s | 0.116 s | 0.076 s | 0 network requests, 4 mocked generation calls | 0 | 4 |

Each cold run started with zero cache rows and generated four entries. Each warm run prepared four questions from those rows and called the generator zero times, including the second authorized user opening the deck without saving a copy. The online test used Ollama 0.40.17 with `qwen3:1.7b` and a 20-second timeout per attempt. The network-isolated run used the real HTTP client pointed at an unavailable loopback port. The mocked runs exercised the same pipeline with predictable generator responses. These are single-run measurements from a solo start request to the ready state, or from room lobby configuration and start to the ready countdown. Room timings exclude the intentional five-second countdown. They do not establish large-deck throughput.

The concurrency regression uses independent event loops and SQLite connections to request the same cold card together. It observes one generator invocation and the same committed three choices for both callers. A separate Docker smoke check confirmed the same result with two independent OS processes and a simulated model. Tests also cover cancellation, reclaiming an expired lease, fencing an old writer, and reading persisted entries after reopening SQLite. The Docker app retains its existing single-worker session coordinator. A worker killed without cleanup can leave its card leased until expiry, which is three configured model attempt timeouts plus 15 seconds. The DB never holds a write transaction open during inference.

## Regression results

- Backend suite: 558 passed. The opt-in provider test was skipped in the default run and passed separately with Ollama online and unreachable.
- Frontend suite: 74 passed. The Vite production build passed.
- The focused Docker browser flow passed in two browsers with Ollama unreachable. It covered room preparation, publication of the same deck, server-backed shared study, and redirecting an older shared-practice URL. The complete browser run stopped at the existing invitation-pagination check before reaching shared study.

## Reproduce

From the repository, build the backend image and run the focused tests using a disposable container and a read-only source mount:

```powershell
docker compose build backend
$source = (Resolve-Path backend).Path
docker run --rm --network none --mount "type=bind,source=$source,target=/app,readonly" -e DATABASE_URL=sqlite:////tmp/shared-distractors.db queezo-backend:latest python -m pytest -q -s tests/test_study_rooms.py tests/test_distractor_cache.py -k "distractors_shared or version_two_migration"
docker run --rm --mount "type=bind,source=$source,target=/app,readonly" -e DATABASE_URL=sqlite:////tmp/shared-distractors.db -e QUEEZO_TEST_LIVE_SHARED=1 -e OLLAMA_BASE_URL=http://host.docker.internal:11434 -e OLLAMA_MODEL=qwen3:1.7b -e OLLAMA_REQUEST_TIMEOUT_SECONDS=20 queezo-backend:latest python -m pytest -q -s tests/test_study_rooms.py -k live-ollama
```

For the unreachable-provider run, add `--network none` and set `OLLAMA_BASE_URL=http://127.0.0.1:11434` on the final command. The two-browser check in [Study Rooms](../STUDY_ROOMS.md) also exercises cached shared-deck solo practice after a room prepares the deck. See [cache policies and operator refresh](../OLLAMA.md) for invalidation rules. Text checks exclude blank choices, duplicates, and normalized copies of the correct answer. Distractors can still be ambiguous or correct in context.
