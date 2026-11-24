# Activity diagrams · Study Rooms

[Architecture index](../../README.md) · [Study Rooms](../../06-multiplayer-study-rooms.md)

## Collaborative and Challenge gameplay

![Collaborative and Challenge question workflows](../rendered/room-gameplay.svg)

```plantuml
@startuml
start
:Host starts with authorized deck and ready lineup;
:Persist roster and shuffled round sequence;
:Prepare options using shared cache and run opening countdown;
while (Playable round and active authorization?) is (yes)
  if (Next position pending?) then (yes)
    :Wait while preparation settles;
  else (question ready)
    :Open question and accept at most one option per player;
    if (Challenge?) then (yes)
      :Wait for eligible answers or server deadline;
      :Score correct answers by elapsed time;
    else (Collaborative)
      :Wait for eligible answers;
      :Record answered and correct counts;
    endif
    :Reveal correct option and player selections;
    :Hold five-second review;
    if (Collaborative host pauses?) then (yes)
      :Wait for resume or state recovery;
    endif
    :Advance past resolved round and permanent failures;
  endif
endwhile (no)
:Persist result if session can finish;
:Host returns to lobby or leaves the room;
stop
@enduml
```

The engine may finish early when the deck grant is lost or no eligible players remain. A pending position never runs an answer timer. The client draws the reveal using a committed viewer-specific snapshot.

Sources [lobby checks](../../../../backend/app/services/study_rooms.py), [round engine](../../../../backend/app/services/room_study.py), [room view](../../../../frontend/src/views/RoomView.vue).

## Room joining and invitation validation

![Invitation validation and joining](../rendered/room-joining.svg)

```plantuml
@startuml
start
:Authenticate caller and require CSRF for invite response;
if (Accept and already joined to open room?) then (yes)
  :Return existing membership outcome;
  stop
endif
if (Pending invite for this caller and open room?) then (yes)
  if (Accept?) then (yes)
    if (Sender still member, friend accepted and room has capacity?) then (yes)
      if (Room in lobby?) then (yes)
        :Insert lobby participant;
      else (no)
        :Insert spectator;
      endif
    else (no)
      :Reject invalid or full invite;
      stop
    endif
  endif
  :Delete pending invite and commit;
  :Refresh invitation state;
else (no)
  :Return unavailable;
endif
stop
@enduml
```

An accepted friend invitation is necessary for new membership. The server validates against the current database when the invite is used. A requester can decline an open invite even when the sender would no longer qualify for acceptance.

Sources [room invite response](../../../../backend/app/services/study_rooms.py), [CSRF and route](../../../../backend/app/auth/middleware.py), [Room API](../../../../backend/app/routers/study_rooms.py).
