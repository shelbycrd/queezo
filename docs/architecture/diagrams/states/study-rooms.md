# State machines · Study Rooms

[Architecture index](../../README.md) · [Study Rooms](../../06-multiplayer-study-rooms.md)

## Room lifecycle

```mermaid
stateDiagram-v2
  [*] --> Lobby : Room and host created
  state "Active study" as Active
  Lobby --> Active : Host starts ready roster
  Active --> Results : Questions exhausted, grant lost, or no eligible players
  Results --> Lobby : Host resets
  Lobby --> Closed : Host ends or room is empty or idle
  Active --> Closed : Host ends or room is empty or idle
  Results --> Closed : Host ends or room is empty or idle
  Closed --> [*]
```

Active study groups five persisted room phases. Host handoff can occur within an existing phase. Closure hides the room from membership reads and clears outstanding invites. Closed rows are retained.

Sources [membership, closure, and reset](../../../../backend/app/services/study_rooms.py), [clock](../../../../backend/app/services/room_study.py).

## Multiplayer session lifecycle

```mermaid
stateDiagram-v2
  [*] --> Preparing : Host starts and persists roster
  Preparing --> Countdown : Readiness threshold or settled with playable options
  Preparing --> Results : Settled with no playable questions
  Countdown --> Open : Five seconds and next position ready
  Countdown --> Waiting : Next position still pending
  Countdown --> Results : No playable position remains
  Open --> Reveal : Eligible answers complete or Challenge deadline
  Reveal --> Open : Review elapses and next position ready
  Reveal --> Waiting : Review elapses and next position still pending
  Waiting --> Open : Position or later playable position resolves
  Waiting --> Results : No playable positions remain
  Reveal --> Results : No playable positions remain
  Preparing --> Results : Deck grant lost or eligible roster empty
  Countdown --> Results : Deck grant lost or eligible roster empty
  Open --> Results : Deck grant lost or eligible roster empty
  Waiting --> Results : Deck grant lost or eligible roster empty
  Reveal --> Results : Deck grant lost or eligible roster empty
  Results --> [*] : Reset lobby or close
```

The phases come from the owning room's `phase`. `RoomSession` stores the active position, deadlines, claims, and result data. Closure can stop any phase, as shown in the room lifecycle above. Preparation continues while rounds play, and permanent failures are skipped by ordered advancement.

Sources [round progression](../../../../backend/app/services/room_study.py), [room lifecycle](../../../../backend/app/services/study_rooms.py).

## Invitation lifecycle

```mermaid
stateDiagram-v2
  [*] --> Pending : Host creates invite for accepted friend
  Pending --> Pending : Repeat invite or accept denied by current checks
  Pending --> Accepted : Valid invitee accepts and membership is inserted
  Pending --> Declined : Invitee declines
  Pending --> Unavailable : Room closes or identity deleted
  Accepted --> [*]
  Declined --> [*]
  Unavailable --> [*]
```

Only the pending invite is a persisted invite record. Acceptance creates membership and deletes that record. Decline and cleanup also remove it. A lost friendship or sender membership can prevent acceptance while the row stays pending.

Sources [invite create, join and close](../../../../backend/app/services/study_rooms.py), [FK deletion rules](../../../../backend/app/models.py).

## Individual round lifecycle

```mermaid
stateDiagram-v2
  [*] --> Pending : Ordered placeholder
  Pending --> Prepared : Save options and correct ID
  Pending --> Failed : Invalid source or preparation exhausted
  Prepared --> Answering : Engine opens current question
  Answering --> Answering : Eligible player locks answer and others remain
  Answering --> Reveal : All eligible answered or Challenge deadline
  Reveal --> Paused : Host pauses Collaborative review
  Paused --> Reveal : Host resumes or host handoff clears pause
  Reveal --> Advanced : Review deadline elapsed
  Answering --> Aborted : Deck grant lost or eligible roster empty
  Reveal --> Aborted : Deck grant lost or eligible roster empty
  Paused --> Aborted : Deck grant lost or eligible roster empty
  Failed --> [*]
  Advanced --> [*]
  Aborted --> [*]
```

These round states are derived from persisted options, failure, answers, room phase, and session clocks. Failed questions cannot open. The server records one option per eligible player and grants no scoring credit for a missing answer.

Sources [question model](../../../../backend/app/models.py), [round methods](../../../../backend/app/services/room_study.py), [pause route](../../../../backend/app/routers/study_rooms.py).
