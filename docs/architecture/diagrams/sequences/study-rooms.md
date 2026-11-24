# Sequence diagrams · Study Rooms

[Architecture index](../../README.md) · [Study Rooms](../../06-multiplayer-study-rooms.md) · [State machines](../states/study-rooms.md)

## Room creation and invitation

```mermaid
sequenceDiagram
  actor Host
  participant UI as Room UI
  participant API as Room REST API
  participant Service as study_rooms service
  participant DB as SQLite
  participant Engine as RoomEngine
  Host->>UI: Invite an accepted friend
  UI->>API: POST /api/rooms with invitee username
  API->>Service: Authenticated creation in a write transaction
  Service->>DB: Check accepted friendship and room limits
  Service->>DB: Insert room, host membership and invite
  API-->>UI: 201 with room ID
  API->>Engine: After commit, wake affected account listeners
  opt Invite a friend to an existing room
    UI->>API: POST room /invite
    API->>Service: Validate host, target and eligibility
    Service->>DB: Persist invite
    API->>Engine: Wake after commit
  end
```

The host must be authenticated and the invite targets an accepted friend. The notification wakeup follows a committed write. Pending invites can be rediscovered through the durable overview.

Sources [routes](../../../../backend/app/routers/study_rooms.py), [creation and eligibility](../../../../backend/app/services/study_rooms.py).

## Live invitation delivery

```mermaid
sequenceDiagram
  participant UI as RoomInvitations
  participant Edge as Vite or Nginx
  participant API as Rooms REST API
  participant WS as Notification WebSocket
  participant Engine as RoomEngine registry
  participant DB as SQLite
  UI->>Edge: Connect /api/rooms/notifications/live
  Edge->>WS: Upgrade and forward Origin and cookie
  WS->>DB: Validate session and read account-scoped overview
  WS-->>UI: Initial snapshot
  WS->>Engine: Wait for account wakeup or polling timeout
  Engine-->>WS: Wake on committed invite change
  WS->>DB: Revalidate session and load latest snapshot
  WS-->>UI: Changed overview or periodic heartbeat
  opt Socket fails or reconnects
    UI->>Edge: GET /api/rooms for durable recovery
    Edge->>API: Forward overview request
    API->>DB: Read current invitations
    API-->>Edge: Account-scoped overview
    Edge-->>UI: Current overview via backend
  end
```

The browser receives snapshots for its own account. The process-local wakeup reduces latency. The polling fallback and REST fetch do not depend on the wakeup reaching an existing socket.

Sources [notification handler](../../../../backend/app/routers/study_rooms.py), [room engine](../../../../backend/app/services/room_study.py), [Vue invitation component](../../../../frontend/src/components/RoomInvitations.vue).

## Join and readiness

```mermaid
sequenceDiagram
  actor Invitee
  participant UI as Room UI
  participant API as Room API
  participant DB as SQLite
  Invitee->>UI: Accept invitation
  UI->>API: POST room /invitation with accept=true
  API->>DB: Verify invitee, live sender, friendship and capacity
  alt Valid invite or already joined
    API->>DB: Insert member if needed and consume invite
    API-->>UI: 204
    UI->>API: GET room snapshot, then connect room /live
    API-->>UI: Current phase and participant view
    alt Lobby participant
      UI->>API: POST room /ready
      API->>DB: Validate lobby, membership and connected eligible guest
      API->>DB: Save ready state
    else Joined during a session
      Note over UI,DB: Spectator until lobby reset
    end
  else Missing invitation, invalid sender or full room
    API-->>UI: Authorization, availability or capacity error
  end
```

The host selects settings separately. Starting requires a connected host and enough connected, ready players. Mid-session participants cannot enter the persisted player roster.

Sources [join and readiness routes](../../../../backend/app/routers/study_rooms.py), [authorization and roster](../../../../backend/app/services/study_rooms.py).

## Collaborative submission and reveal

```mermaid
sequenceDiagram
  actor Player
  participant UI as RoomView
  participant API as Room REST API
  participant Logic as room_study
  participant DB as SQLite
  participant WS as Room snapshot stream
  Player->>UI: Select answer
  UI->>API: POST room /answer with session, position and option
  API->>Logic: Verify membership, roster, question and allowed option
  Logic->>DB: Persist the locked answer
  alt Pending eligible players
    Logic-->>API: Keep question open
    DB-->>WS: Viewer-specific question snapshot
    WS-->>UI: Own selection only
  else All eligible players answered
    Logic->>DB: Persist reveal and five-second review deadline
    DB-->>WS: Reveal snapshot with correct option and selections
    WS-->>UI: Draw correct choice and player avatars
  end
  opt Host pauses or resumes review
    API->>Logic: Guarded room /pause with current session and position
    Logic->>DB: Clear or renew review deadline
  end
  Logic->>DB: Advance after review deadline or wait for preparation
```

The final accepted submission can trigger reveal in the same transaction. The clock also reevaluates eligibility. Collaborative mode has no answer deadline. Review pause is a host action distinct from answering.

Sources [answer and pause routes](../../../../backend/app/routers/study_rooms.py), [round state and projection](../../../../backend/app/services/room_study.py).

## Challenge timer and scoring

```mermaid
sequenceDiagram
  participant Engine as RoomEngine clock
  participant DB as SQLite
  participant WS as Room WebSocket
  actor Player
  participant API as Room REST API
  Engine->>DB: Open question and set server deadline
  WS->>DB: Read current viewer projection
  WS-->>Player: Question and deadline
  Player->>API: POST room /answer
  alt Valid option before deadline
    API->>DB: Lock choice and server receipt time
  else Invalid, duplicate change or late
    API-->>Player: Format or conflict response
  end
  alt All eligible players have answered
    API->>DB: Reveal and score in last submission transaction
  else Deadline reached
    Engine->>DB: Reveal and score on tick
  end
  WS->>DB: Project choices and standings
  WS-->>Player: Correct option, locked choices and updated leaderboard
  Engine->>DB: Advance after five-second review
```

For correct answers, points decay from 1,000 with elapsed time and floor at 100. Wrong or absent answers earn zero. The server owns receipt time, deadlines and scoring. Frame timing does not grant additional answer time.

Source [round execution and scoring](../../../../backend/app/services/room_study.py).

## WebSocket disconnection and reconnection

```mermaid
sequenceDiagram
  participant UI as RoomView / rooms.js
  participant API as Room REST API
  participant WS as Room live handler
  participant Engine as Socket registry and clock
  participant DB as SQLite
  UI->>WS: Connect room /live with session cookie and Origin
  WS->>DB: Validate auth and membership
  WS->>Engine: Register connection
  WS->>DB: Reconnect and refresh presence
  WS-->>UI: Current viewer-specific snapshot
  loop During connection
    WS->>DB: Revalidate and project room state
    WS-->>UI: Changed snapshot or heartbeat
  end
  UI--xWS: Transport disconnects
  WS->>Engine: Remove socket
  opt Last socket for this member
    WS->>DB: Record disconnect unless superseded by newer presence
  end
  UI->>API: Read current room for REST recovery
  API->>DB: Revalidate membership and project current room
  API-->>UI: Current room snapshot
  UI->>WS: Reconnect and authenticate
  WS->>DB: Restore presence and read same session and position
  WS-->>UI: Current snapshot
```

The database retains the round. A dropped socket starts a grace period. If the player stays away, the engine reevaluates eligibility and can hand off a disconnected host. Another valid tab can keep membership connected.

Sources [room socket and disconnect handling](../../../../backend/app/routers/study_rooms.py), [client transport](../../../../frontend/src/services/rooms.js), [clock and host handling](../../../../backend/app/services/room_study.py).

## Host handoff and termination

```mermaid
sequenceDiagram
  actor Host
  participant API as Room REST API
  participant Engine as RoomEngine
  participant DB as SQLite
  Host->>API: POST room /leave
  API->>DB: Authorize membership and inspect current host
  alt Host explicitly ends room or no replacement remains
    API->>DB: Mark room closed and delete pending invites
    API->>Engine: Wake affected account listeners after commit
  else Host leaves with another member present
    API->>DB: Assign earliest-joined remaining member
    API->>DB: Delete departing membership and reevaluate deck grant
  else Non-host leaves
    API->>DB: Delete departing membership
  end
  opt Automatic recovery
    Engine->>DB: Inspect stale connections and room activity
    alt Host past grace with a connected successor
      Engine->>DB: Assign earliest-joined connected member
    else Empty or idle room
      Engine->>DB: Close room and clear pending invites
    end
  end
```

The explicit and automatic handoff paths use different eligibility rules. Private-deck access depends on the owner remaining in the room. A revoked grant can end the active session. Closed rooms are unavailable to normal membership reads.

Sources [leave route](../../../../backend/app/routers/study_rooms.py), [join-order, closure and grant](../../../../backend/app/services/study_rooms.py), [automatic recovery](../../../../backend/app/services/room_study.py).
