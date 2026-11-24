# UML components

[Architecture index](../README.md) · [Component responsibilities](../02-architecture-and-components.md)

## Browser components

![Browser components and external interfaces](rendered/browser-components.svg)

```plantuml
@startuml
left to right direction
package "Vue application" {
  component "main.js / App.vue" as Shell
  component "session.js / AuthView.vue" as Session
  component "ProfileView / ProfileSettings / PeopleView" as Profile
  component "FriendsDrawer / friends.js" as Friends
  component "RoomInvitations / rooms.js" as Invites
  component "DecksView / DeckView / SharedView" as Deck
  component "StudyOptions / StudyView / MultipleChoiceView" as Solo
  component "RoomView / RoomChat" as Rooms
  component "GwaView" as Gwa
  component "PomodoroView / pomodoro.js" as Pomo
}
interface "Same-origin JSON API" as HTTP
interface "Room and invitation snapshots" as WS
interface "Browser storage and notifications" as Local
Shell --> Session : bootstrap
Shell --> Profile : route
Shell --> Friends : drawer
Shell --> Invites : mounted listener
Shell --> Deck : route
Shell --> Solo : route and dialog
Shell --> Rooms : route
Shell --> Gwa : route
Shell --> Pomo : route
Session ..> HTTP : session and CSRF
Profile ..> HTTP
Friends ..> HTTP
Invites ..> HTTP : overview recovery
Invites ..> WS
Deck ..> HTTP
Solo ..> HTTP
Rooms ..> HTTP : commands
Rooms ..> WS : snapshots
Gwa ..> HTTP
Pomo ..> HTTP : activity
Pomo ..> Local
@enduml
```

The root shell mounts notifications and shared UI. The Vue Router selects feature views. Session bootstrap supplies authenticated identity and CSRF to same-origin requests. Room socket transport lives in `rooms.js`. Pomodoro's clock runs in the browser.

Sources [Vue entrypoint](../../../frontend/src/main.js), [root shell](../../../frontend/src/App.vue), [session](../../../frontend/src/services/session.js), [room transport](../../../frontend/src/services/rooms.js), [Pomodoro](../../../frontend/src/services/pomodoro.js).

## Backend components

![Backend modules, shared data and inference interfaces](rendered/backend-components.svg)

```plantuml
@startuml
left to right direction
interface "Application REST and sockets" as AppAPI
interface "GWA REST" as GwaAPI
interface "Ollama /api/chat" as Ollama
database "SQLite / SQLAlchemy models" as DB
package "backend · app.main" {
  component "auth router / service / dependencies" as Auth
  component "auth middleware / limits" as Guards
  component "profiles / friends / activity" as Social
  component "decks / community / ownership" as Decks
  component "study / study_scheduler" as Classic
  component "multiple_choice router and service" as MC
  component "study_rooms router and service" as Rooms
  component "room_study.RoomEngine" as Engine
  component "distractor_cache" as Cache
  component "distractors" as AI
}
package "gwa · app.gwa.main" {
  component "GWA route and calculator" as Gwa
}
AppAPI --> Guards
Guards --> Auth
Guards --> Social
Guards --> Decks
Guards --> Classic
Guards --> MC
Guards --> Rooms
Auth --> DB
Social --> DB
Decks --> DB
Classic --> DB
MC --> DB : sessions and snapshots
Rooms --> DB : room commands and projections
Rooms --> Engine : socket registry and wakeup
Engine --> DB : claims, rounds and scoring
MC --> Cache
Engine --> Cache
Cache --> DB : cards, sources and leases
Cache --> AI
AI ..> Ollama
GwaAPI --> Gwa
Gwa ..> Auth : shared Python session dependency
@enduml
```

The boxes group real Python files by responsibility. GWA imports shared authentication code inside its own process. It does not make network calls to the main backend. Notification snapshots use the room router and engine registry.

Sources [backend assembly](../../../backend/app/main.py), [room router](../../../backend/app/routers/study_rooms.py), [room engine](../../../backend/app/services/room_study.py), [cache](../../../backend/app/services/distractor_cache.py), [GWA API](../../../backend/app/gwa/main.py).
