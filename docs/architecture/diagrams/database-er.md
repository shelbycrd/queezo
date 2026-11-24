# Physical database ER

[Architecture index](../README.md) · [Table catalog](../03-database-design.md) · [Domain classes](domain-classes.md)

These diagrams identify physical primary and foreign keys in the initialized SQLite schema. Repeated entity names connect the subgraphs. Scalar attributes are selective. Solid lines denote identifying relationships, and dotted lines denote non-identifying relationships.

## Identity and account activity

```mermaid
erDiagram
  users {
    int id PK
    string uid UK
    string username UK
    string email UK
    int featured_deck_id FK "nullable"
  }
  decks {
    int id PK
    int owner_id FK "nullable"
  }
  auth_sessions {
    string token_hash PK
    int user_id FK
    datetime expires_at
  }
  login_throttles {
    string key PK
    datetime window_started
    int attempts
  }
  session_presence {
    string session_hash PK, FK
    datetime seen_at
  }
  friendships {
    int first_id PK, FK
    int second_id PK, FK
    int requester_id
  }
  profile_avatar_changes {
    int id PK
    int user_id FK
  }
  profile_reports {
    int id PK
    int target_id FK
    int reporter_id FK
  }
  activity_days {
    int user_id PK, FK
    date day PK
  }
  users |o..o{ decks : owns
  decks |o..o{ users : featured_on
  users ||..o{ auth_sessions : authenticates
  auth_sessions ||--o| session_presence : tracks
  users ||--o{ friendships : first_endpoint
  users ||--o{ friendships : second_endpoint
  users ||..o{ profile_avatar_changes : changes
  users ||..o{ profile_reports : reported
  users ||..o{ profile_reports : reports
  users ||--o{ activity_days : studied
```

Usernames and emails are case-insensitive unique keys. Friendship columns are the sorted participants, with the requester constrained to one endpoint. Reports have distinct reporter and target IDs. Rate-limit buckets use an independent key.

Sources [identity models](../../../backend/app/models.py), [legacy identity and profile migrations](../../../backend/app/profile_migration.py).

## Content, shared cache, and solo study

```mermaid
erDiagram
  users {
    int id PK
  }
  decks {
    int id PK
    int owner_id FK
    string share_token UK "nullable"
  }
  flashcards {
    int id PK
    int deck_id FK
    text front
    text back
  }
  flashcard_distractor_cache {
    int flashcard_id PK, FK
    json distractors "three values"
    string content_fingerprint
    int generation_version
  }
  flashcard_distractor_sources {
    int flashcard_id PK, FK
    int position PK "slot 0 to 2"
    int source_card_id FK
    string content_fingerprint
  }
  flashcard_distractor_jobs {
    int flashcard_id PK, FK
    string token
    datetime expires_at
  }
  study_sessions {
    string id PK
    int owner_id FK "nullable"
    int deck_id FK
    string status
  }
  study_session_cards {
    int id PK
    string session_id FK
    int flashcard_id FK "nullable"
    int initial_order
  }
  study_reviews {
    int id PK
    string session_id FK
    int session_card_id FK
    int presentation_number
  }
  multiple_choice_sessions {
    string id PK
    int owner_id FK
    int deck_id FK
    string status
    string shared_access
  }
  multiple_choice_questions {
    string id PK
    string session_id FK
    int source_card_id "logical reference"
    int position
    string correct_option_id
  }
  users |o..o{ decks : owns
  decks ||..o{ flashcards : contains
  flashcards ||--o| flashcard_distractor_cache : caches
  flashcard_distractor_cache ||--o{ flashcard_distractor_sources : describes
  flashcards ||..o{ flashcard_distractor_sources : provides
  flashcards ||--o| flashcard_distractor_jobs : leases
  users |o..o{ study_sessions : starts
  decks ||..o{ study_sessions : studies
  study_sessions ||..o{ study_session_cards : snapshots
  flashcards |o..o{ study_session_cards : sourced_from
  study_sessions ||..o{ study_reviews : records
  study_session_cards ||..o{ study_reviews : rates
  users ||..o{ multiple_choice_sessions : starts
  decks ||..o{ multiple_choice_sessions : studies
  multiple_choice_sessions ||..o{ multiple_choice_questions : snapshots
```

Classic snapshot order and review presentation identifiers are unique within a session. Solo Multiple-Choice positions and original card IDs are likewise unique within each session. Options and the correct option are recorded together. A missing live card does not remove its already prepared solo snapshot. SQLite triggers invalidate changed cache dependencies and enforce the 150-card cap.

Sources [models](../../../backend/app/models.py), [SQLite schema and baseline indexes](../../../backend/app/database.py).

## Multiplayer

```mermaid
erDiagram
  users {
    int id PK
  }
  decks {
    int id PK
  }
  flashcards {
    int id PK
  }
  study_rooms {
    string id PK
    int host_id FK "nullable"
    int deck_id FK "nullable"
    string session_id "logical reference"
    string phase
  }
  study_room_members {
    string room_id PK, FK
    int user_id PK, FK
    datetime joined_at
    bool ready
    bool spectator
  }
  study_room_invites {
    string room_id PK, FK
    int user_id PK, FK
    int sender_id FK
  }
  study_room_sessions {
    string id PK
    string room_id FK
    json players
    json scores
    datetime deadline
  }
  study_room_questions {
    string session_id PK, FK
    int position PK
    int card_id FK "nullable"
    json options
    json answers
  }
  study_room_messages {
    int id PK
    string room_id FK
    int sender_id FK "nullable"
    json author
  }
  users |o..o{ study_rooms : hosts
  decks |o..o{ study_rooms : selected_in
  study_rooms ||--o{ study_room_members : registers
  users ||--o{ study_room_members : joins
  study_rooms ||--o{ study_room_invites : issues
  users ||--o{ study_room_invites : receives
  users ||..o{ study_room_invites : sends
  study_rooms ||..o{ study_room_sessions : plays
  study_room_sessions ||--o{ study_room_questions : owns
  flashcards |o..o{ study_room_questions : sourced_from
  study_rooms ||..o{ study_room_messages : contains
  users |o..o{ study_room_messages : authors
```

Room and user form the member and invitation keys. Room-session ID and position identify a round. Player roster, submitted answers, and standings are stored JSON values, without individual answer rows. The service manages the current session and deck-owner grant as logical pointers.

Sources [room models](../../../backend/app/models.py), [lifecycle service](../../../backend/app/services/room_study.py).
