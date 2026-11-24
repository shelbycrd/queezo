# 08 · Data flows and lifecycle

[Architecture index](README.md)

## State and clock ownership

| State | Authority | How the browser recovers |
| --- | --- | --- |
| Account session and CSRF | SQLite token digest and expiry. Session cookie is browser-managed. | Fetch `/api/auth/me` to restore the authenticated user and CSRF token. |
| Decks, cards, and library | SQLite owner and visibility checks | Reload the route. Shared views resolve the current token. |
| Owned Classic | Backend session and presentation history. Optional browser timing is separate. | Reload the session ID to obtain the current presentation. |
| Solo Multiple-Choice | SQLite stable positions, option snapshots, attempts, status, and server clock | Poll session state and request the current question at the same position. |
| Room, invite, and round | Committed SQLite rows. Workers drive deadlines and eligibility. | Initial REST snapshot, followed by authenticated WebSocket snapshots. REST recovers invitation state if sockets are unavailable. |
| GWA | Request-local weighted calculation | Enter course values and calculate. The server has no grade history. |
| Pomodoro | Account-scoped browser storage with deadline-based countdown | Browser reload restores local state. Completed study reports activity to the backend. |

[Session bootstrap](../../frontend/src/services/session.js), [Classic routes](../../backend/app/routers/study.py), [Multiple-Choice routes](../../backend/app/routers/multiple_choice.py), [Room routes](../../backend/app/routers/study_rooms.py), [GWA calculation](../../backend/app/gwa/service.py), [Pomodoro service](../../frontend/src/services/pomodoro.js)

## Main request paths

- The browser sends same-origin API requests. Nginx routes GWA to its own FastAPI app and main requests to the backend. Authentication dependencies can reject a request before its service reads or writes domain state.
- Solo study exchanges commands over REST and polls for readiness. Rooms use REST commands with server-validated state and read-only socket snapshots. Identifiers and server clocks disambiguate stale browser actions.
- Both question workers resolve distractors through a shared cache. Cache operations are distinct from session snapshots and model calls. Polling does not execute inference.
- Account presence, room presence, and Pomodoro have separate clocks. Account heartbeat determines social availability. Room connection presence and grace determine eligibility and handoff. The Pomodoro display reads the local browser clock while streak dates are computed by the backend in Asia/Manila.

[Browser API and router](../../frontend), [backend assembly](../../backend/app/main.py), [presence](../../backend/app/services/presence.py), [activity](../../backend/app/services/activity.py)

## Scenario index

| Question | Diagram |
| --- | --- |
| How are credentials and sessions handled? | [Registration and login](diagrams/sequences/accounts-and-cards.md#registration-and-login) |
| How does card editing affect distractors? | [Edit and invalidate](diagrams/sequences/accounts-and-cards.md#edit-and-invalidate) |
| How does a solo session become playable? | [Solo session initialization](diagrams/sequences/solo-and-ai.md#solo-session-initialization) and [progressive question loading](diagrams/activities/multiple-choice.md#progressive-question-loading) |
| When do model calls and fallback run? | [Generation and persistence](diagrams/sequences/solo-and-ai.md#generation-and-persistence) and [distractor states](diagrams/states/distractors.md) |
| How are room invitations delivered? | [Live invitation delivery](diagrams/sequences/study-rooms.md#live-invitation-delivery) |
| How do rounds and reconnects work? | [Study Room sequences](diagrams/sequences/study-rooms.md), [state machines](diagrams/states/study-rooms.md) |
