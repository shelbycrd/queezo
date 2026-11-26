# 06 · Multiplayer Study Rooms

[Architecture index](README.md) · [Room sequences](diagrams/sequences/study-rooms.md) · [State machines](diagrams/states/study-rooms.md) · [Activities](diagrams/activities/study-rooms.md)

## Membership and lobby

Creation authorizes the inviter and accepted friend before persisting the room, host membership, and initial invite in one write transaction. A room supports up to six members. The host can invite accepted friends. Invite acceptance verifies the invitee, current sender membership, friendship, capacity, and room availability. Accepting again as an existing member is idempotent. Joining mid-session produces a spectator who can read the room and chat. Only players in the starting roster can answer. A lobby reset clears spectator and readiness flags. [Room API](../../backend/app/routers/study_rooms.py), [room service](../../backend/app/services/study_rooms.py)

Invitations are rate limited per sender-recipient pair: five attempts in a rolling 60-second window, recorded in fixed `login_throttles` slots inside the `BEGIN IMMEDIATE` write transaction, so concurrent requests serialize and cannot bypass the limit. Room creation and in-room invites share the same limit. Exceeding it returns 429 with a fixed message and no limit, remaining-attempt, or cooldown details (no `Retry-After`). A sender holds at most one active invitation per recipient: repeating "Invite to Study" reuses the pending lobby, and inviting the same friend into another room supersedes the older invitation. The recipient's notification socket pushes the change; the frontend shows a popup with Accept and Decline for invitations that arrive after the first snapshot, while the Notifications panel keeps the persisted list and badge count in sync. [Invitation popup](../../frontend/src/components/RoomInvitations.vue)

Room URLs use the public code (`/rooms/2C9F10C8`), never the UUID. `GET /api/rooms/resolve/{code}` maps a code, or a legacy UUID link, to the room only for its current members. Unknown, closed, and non-member rooms return the same 404, and each miss counts toward a per-account lookup throttle that returns 429. Membership, invitation, and deck checks still run on the UUID-based room APIs, so a known code grants nothing. New codes come from `secrets` with a uniqueness check inside the serialized write transaction, backed by a unique index. [Room entry](../../frontend/src/views/RoomEntry.vue)

The host selects a permitted deck, gameplay mode, and Challenge duration. Public deck selection can come from another owner. Private or unlisted content is exposed to members through a room-scoped grant tied to the deck owner. Relevant setting changes reset readiness. The browser submits a revision when changing settings so a stale form cannot silently replace a fresher configuration. Start requires a connected host and at least one connected ready guest, with every eligible guest in the connected lineup ready. The transaction snapshots roster, ordered questions, and the current session ID. [Settings and start](../../backend/app/services/study_rooms.py), [lobby UI](../../frontend/src/views/RoomView.vue)

## Preparation, questions, and scoring

`RoomEngine` claims preparation work in SQLite and refreshes its lease while generating. It uses the same persistent cache as solo study. The opening readiness rule starts a five-second countdown when at least five questions are ready, or when preparation settles with at least one playable question. For decks under five cards, the threshold uses the deck size. After countdown, the engine opens a question and records its timestamps. A gap for a pending question pauses gameplay until that question settles. Source changes and revoked grants are checked when needed. [Room preparation and clock](../../backend/app/services/room_study.py)

| Concern | Collaborative | Challenge |
| --- | --- | --- |
| Answer window | One locked option per eligible player. Waits for eligible players. | One locked option before the server deadline. Runs for 10–120 seconds, default 30. |
| Reveal trigger | All eligible players have answered. | All eligible players have answered, or the deadline expires. |
| Reveal | Correct option and submitted choices become visible. | Same disclosure, with score updates. |
| Next question | Five-second review. Host can pause or resume discussion with a guarded round command. | Five-second review before automatic progression. |
| Scoring | Group feedback, no timed leaderboard. | Correct answer earns `max(100, half_up(1000 − 30 × elapsed_seconds))`. Wrong or absent earns zero. Standings break ties by correct count and username. |

Writes include session ID and position. Membership, eligibility, phase, option ID, and deadline are checked inside the write transaction. Repeating the same lock within the open round is idempotent. The public snapshot conceals the correct option and other players' selections until reveal. If players disappear or a deck becomes invalid, the engine can finish with results recorded so far. [Round progression and projections](../../backend/app/services/room_study.py)

## WebSockets, ordering, and recovery

| Channel | Direction and use | Recovery |
| --- | --- | --- |
| `/api/rooms/notifications/live` | Authenticated, account-scoped room/invite snapshots. A notification event wakes the handler after a committed write, with a five-second polling fallback. | The frontend can get a durable overview with `GET /api/rooms`. |
| `/api/rooms/{room_id}/live` | Authenticated room snapshots. Reads are viewer-specific and membership is revalidated. The loop checks for changes about every 750 ms and sends heartbeat frames. | REST snapshot followed by socket reconnect. Socket reconnect refreshes presence without reinitializing the round. |
| Room REST commands | CSRF-protected mutations for invites, readiness, answers, chat, host actions, and leave. | Persisted session, revision, option IDs, deadline, and state allow retries according to each command's guard. |

The server tracks live connections per member. Closing the last connection marks a disconnect, subject to a fresh-touch guard, and another tab or reconnection can maintain or restore presence. Presence becomes stale after roughly 20 seconds. A 45-second grace period determines continued eligibility and host recovery after a disconnect. Explicit host leave immediately picks the earliest-joined remaining member. Automatic handoff after grace selects the earliest connected member. Host end or an empty room closes it. The engine also closes idle rooms after 30 minutes and clears pending invites on closure. Database state can support restart recovery. Socket registries and wakeups are process-local. [Socket handlers](../../backend/app/routers/study_rooms.py), [host and idle processing](../../backend/app/services/room_study.py), [browser transport](../../frontend/src/services/rooms.js)

Room chat is persistent plain text, restricted to current members, limited to 500 characters and five messages per ten seconds per sender. The room retains up to 500 messages and projects the latest 80. Chat is scoped to the room. [Chat implementation](../../backend/app/services/study_rooms.py)
