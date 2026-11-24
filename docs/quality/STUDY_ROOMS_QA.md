# Multiplayer Study Rooms QA

**Assessment: Ready for Beta.** The core flows passed in two live browsers and in the backend and frontend suites. The queue and database growth still need production-scale validation.

Audit date: November 24, 2026. Scope covered room membership, invitations, host handoff, setup, gameplay, progressive preparation, timers and scoring, chat, notifications, spectators, reconnects, mobile and keyboard behavior, authentication boundaries, SQLite, and the Docker/Nginx path. Browser and API checks used synthetic accounts and decks in an isolated loopback-only Compose project. Backend tests used temporary SQLite databases. The regular Queezo stack and its data were left in place.

## A. Test summary

| Check | Result | Evidence |
| --- | --- | --- |
| Existing backend baseline | 550 passed | Full pytest suite with disposable SQLite and no network |
| Existing frontend baseline | 76 passed | Node test suite |
| Existing browser baseline | 1 passed | Full Playwright scenario through Docker, Nginx, and Vite |
| New backend checks against original behavior | 0 passed, 3 failed as expected | Stale review, first reconnect snapshot, and departure of all active players |
| Post-fix frontend | 76 passed | Node test suite and Vite production build |
| Post-fix browser | 1 passed | Full Playwright scenario with two accounts, desktop and mobile, plus a second tab |
| Post-fix backend | 552 passed | Full pytest suite, 218.44 seconds |
| Final room backend rerun | 16 passed | Includes exact deadline boundary checks, 66.39 seconds |
| Browser restart variant | 1 passed | Full scenario with an isolated backend restart during a question |

The table accounts for **1,276 executions** across all runs, including reruns. **1,273 passed** and **3 intentionally failed before the fixes**. The two backend passes emitted the existing Starlette test-client deprecation warning.

### Runtime coverage

- Existing backend coverage checked membership, private-deck access and revocation, trusted WebSocket origins, answer visibility before reveal, invalid state transitions, spectator restrictions, authenticated identity, chat limits, room capacity, migration, and cache fallback. Security review used defensive source inspection and existing authorization and isolation checks.
- Both modes started and revealed with server-held session state. Two simultaneous final submissions produced one result per player. Backend checks exercised ordered progressive preparation, a loading gap, failed-question skipping, and stale or duplicate answer rejection. The Challenge boundary accepted a submission one microsecond before its deadline and rejected submissions exactly at and one microsecond after it. The room tests used mocked generation and the browser exercise used deck-answer fallback.
- The browser checked live invitations, private deck selection, deck carousel, mobile drawers, keyboard focus return, no page overflow, synchronized start and review timers, correct and wrong reveal styling, locked answers across refresh, the one-time chat notice, incoming-only chat sound and mute, and host transfer. The mobile lobby also passed at 320 × 540 with a synthetic unbroken 40-character room title. Closing the additional tab left the original room connection active.
- **Bounded load:** 12 local room reads, in four batches of three concurrent requests. All returned successfully. Median response time was 113.8 ms and the maximum was 227.8 ms. The restart variant repeated the reads at a 103.4 ms median and 328.4 ms maximum. These are small loopback samples through Vite and Nginx.
- **Resource snapshot:** Docker sampled the isolated containers before the restart. FastAPI used 4.17% CPU and 79.09 MiB RAM, Nginx used 0.04% CPU and 11.57 MiB, and the Vite development container used 27.01% CPU and 345.8 MiB. These are one-shot measurements, without peak, steady-state, or Ollama resource measurements. Docker Engine 29.9.2 and Docker Compose 5.6.1 ran the test.
- **Backend restart:** After the guest locked an answer in Challenge, restarted the isolated backend container and kept both browser tabs open. The browser reported recovery in 6.73 seconds from issuing the restart through the membership becoming live again. The same question, ordered choices, and locked answer were still visible. The exercise continued through reveal and host transfer.
- **Session expiration:** the targeted test advances a disposable session past expiration and verifies that both room and notification WebSocket state access stops. The browser verified refresh and multi-tab recovery.

Sources: [backend room suite](../../backend/tests/test_study_rooms.py), [browser scenario](../../frontend/tests/e2e/study-rooms.cjs), [cache suite](../../backend/tests/test_distractor_cache.py), and [solo MCQ suite](../../backend/tests/test_multiple_choice.py).

## B. Confirmed issues

No Critical issue was confirmed within the tested scope.

### ROOM-01 · High · A round can strand its remaining spectators

- **Component** — Room lifecycle and scoring. [Room round progression](../../backend/app/services/room_study.py#L100)
- **Scenario** — Play the first round of a public-deck Collaborative session with two players, let a third person join as a spectator, advance, then have both active players leave.
- **Expected** — End the session and retain results from rounds already scored.
- **Actual and cause** — The room stayed on a question nobody could answer. An empty eligible-player set prevented completion, and a connected spectator kept the room open.
- **Fix and evidence** — Finalize active sessions when no eligible players remain after the existing reconnect grace rules apply. The regression verifies simultaneous first-round submissions, the spectator-only transition, and preserved counts.

### ROOM-02 · Medium · The first reconnect snapshot can report the player as disconnected

- **Component** — WebSocket state and membership heartbeat. [Room snapshots](../../backend/app/routers/study_rooms.py#L165)
- **Scenario** — Reconnect a member whose previous connection was marked disconnected and check the first room snapshot.
- **Expected** — The returning player is connected in the first snapshot.
- **Actual and cause** — The snapshot was assembled before the reconnect heartbeat cleared the disconnection state.
- **Fix and evidence** — Recheck authorization during the heartbeat update and compose the response after the connection fields are updated. The synthetic reconnect test reproduced the mismatch. The browser’s extra-tab check covers a separate connection-lifetime case.

### ROOM-03 · Medium · A delayed pause can affect a different or expired review

- **Component** — Collaborative round controls. [Pause handler](../../backend/app/routers/study_rooms.py#L342)
- **Scenario** — Deliver an old host pause action after the room moves to a different review.
- **Expected** — Reject the stale action and leave the current review running.
- **Actual and cause** — The endpoint checked that the room was reviewing but accepted no binding to the original session or question. It also accepted an expired review before the next scheduler tick.
- **Fix and evidence** — Require the session ID and question position and reject expired reviews. The regression checks the rejected stale action, the matching pause/resume path, and the existing host-only check. The frontend sends the current identifiers.

### ROOM-04 · Medium · Keyboard focus can leave a mobile drawer

- **Component** — Mobile Participants and Room Chat drawers. [Drawer handlers](../../frontend/src/views/RoomView.vue#L114)
- **Scenario** — Open a drawer at a phone width and tab beyond its first or last control.
- **Expected** — Focus stays within the drawer, and Escape returns focus to its opener.
- **Actual and cause** — The main column stayed focusable under the scrim. The drawer had an Escape action and initial focus but no modal focus containment.
- **Fix and evidence** — Make the background room controls inert while the drawer is open, add dialog semantics and focus wrapping, and clear drawer state when returning to desktop width. Playwright verified focus stays in the drawer and returns to its opener.

### ROOM-05 · Low · An unbroken host name can overflow the mobile header

- **Component** — Room heading. [Header styles](../../frontend/css/study-rooms.css#L7)
- **Scenario** — Display a 40-character unbroken host name in a 320-pixel-wide room.
- **Expected** — The title wraps and the room fits the viewport.
- **Actual and cause** — The previous flex minimum and heading styles did not give an unbroken name a place to wrap.
- **Fix and evidence** — Allow the title column to shrink and wrap. The 320 × 540 browser assertion checks both heading and document widths.

## C. Fixes and regression coverage

- [Room progression](../../backend/app/services/room_study.py) now settles a session once no eligible players remain, preserving results already recorded.
- [Room routes](../../backend/app/routers/study_rooms.py) align the first reconnect snapshot with membership state and bind Collaborative pause/resume to a live round.
- [Room view](../../frontend/src/views/RoomView.vue) and [styles](../../frontend/css/study-rooms.css) update the pause payload, narrow-heading behavior, and mobile drawer focus handling.
- [Backend tests](../../backend/tests/test_study_rooms.py) and [browser tests](../../frontend/tests/e2e/study-rooms.cjs) cover the fixes. No schema or production configuration change was needed.

## D. Remaining issues and limits

| ID and severity | Evidence and impact | Follow-up |
| --- | --- | --- |
| ROOM-R01 · Medium · Room preparation can wait behind a long deck | The [worker](../../backend/app/services/room_study.py#L309) prepares one claimed room at a time, and solo and room inference share a model slot. Slow model calls can delay another room even when it has cached choices. Identified by code review. The live-model queue and cross-room wait time were not measured. | Benchmark warm and cold rooms concurrently and evaluate fair scheduling within the existing ordered preparation contract. |
| ROOM-R02 · Medium · An eligible player can hold a Collaborative round open | The [round logic](../../backend/app/services/room_study.py#L100) waits for all eligible players and gives Collaborative mode no answer deadline. The fix covers departed players and expired reconnect grace. A connected participant who never answers still delays everyone. This is a self-paced behavior with no host override. | Decide whether to offer an explicit host skip or an optional Collaborative round deadline before widening the release. |
| ROOM-R03 · Medium · Polling and stored snapshots may become expensive at scale | A room socket [rechecks full state](../../backend/app/routers/study_rooms.py#L274) about every 750 ms per tab. [Prepared rows](../../backend/app/services/room_study.py#L279) keep card images per question snapshot. The small read test did not exercise large images, many rooms, or long-running WAL and disk growth. | Measure active sockets, database reads, write wait times, and snapshot growth with representative image-heavy decks. Set a retention policy based on the data. |
| ROOM-R04 · Low · A settings revision can recur | The [settings revision](../../backend/app/services/study_rooms.py#L141) hashes the settings values. If a host changes the room away from and then back to the same state before a draft arrives, the original revision will match again. This was identified by inspection. Browser delay behavior for that sequence was not measured. | Use a monotonic settings version if cross-tab conflicts become a recurring issue. |

## E. Release assessment

Core room behavior is suitable for a controlled beta. Production readiness remains unverified under sustained multi-room traffic, live Ollama contention, long network partitions, real mobile devices, and production TLS/proxy conditions. The browser run used Chromium viewports and local synthetic data. It does not establish behavior for every browser or deployment. Room chats and requests were inspected for existing validation, rendering, and authorization controls. All executed scenarios used local synthetic data, normal application workflows, and isolated defensive regression checks.
