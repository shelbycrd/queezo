# UML domain classes

[Architecture index](../README.md) · [Physical ER](database-er.md)

## Accounts and content

```mermaid
classDiagram
  class Base {
    <<SQLAlchemyDeclarativeBase>>
  }
  class User {
    int id
    str uid
    str username
    str profile_visibility
  }
  class AuthSession {
    str token_hash
    datetime expires_at
  }
  class Friendship {
    int requester_id
    bool accepted
  }
  class Deck {
    str title
    str visibility
    str share_token
  }
  class Flashcard {
    str front
    str back
    str front_image
    str back_image
  }
  Base <|-- User
  Base <|-- AuthSession
  Base <|-- Friendship
  Base <|-- Deck
  Base <|-- Flashcard
  User "1" -- "0..*" AuthSession : account
  User "1" -- "0..*" Friendship : first endpoint
  User "1" -- "0..*" Friendship : second endpoint
  User "0..1" -- "0..*" Deck : owner
  Deck "1" *-- "0..150" Flashcard : contains
  Deck "0..1" -- "0..*" User : featured by
```

Associations show domain and key constraints. They do not imply SQLAlchemy relationship properties. An active account owns every newly created deck. Nullable owner represents legacy rows. Featuring is an optional association with a public deck.

Source [models](../../../backend/app/models.py).

## Solo study and inference

```mermaid
classDiagram
  class FlashcardDistractorCache {
    list distractors
    str content_fingerprint
    str ollama_model
    int generation_version
  }
  class FlashcardDistractorSource {
    int position
    str content_fingerprint
  }
  class FlashcardDistractorJob {
    datetime expires_at
  }
  class StudySession {
    str status
    str random_seed
    int virtual_position
    str presentation_token
  }
  class StudySessionCard {
    int initial_order
    int target_reviews
    bool completed
  }
  class StudyReview {
    str difficulty
    int presentation_number
  }
  class MultipleChoiceSession {
    str status
    int attempt
    datetime prepare_until
    datetime expires_at
  }
  class MultipleChoiceQuestion {
    int source_card_id
    int position
    list options
    str correct_option_id
    str eliminated_option_id
  }
  Flashcard "1" *-- "0..1" FlashcardDistractorCache
  Flashcard "1" *-- "0..1" FlashcardDistractorJob
  FlashcardDistractorCache "1" *-- "0..3" FlashcardDistractorSource : provenance
  Flashcard "1" -- "0..*" FlashcardDistractorSource : fallback source
  Deck "1" *-- "0..*" StudySession
  Deck "1" *-- "0..*" MultipleChoiceSession
  StudySession "1" *-- "0..*" StudySessionCard
  Flashcard "0..1" -- "0..*" StudySessionCard : optional live card
  StudySessionCard "1" *-- "0..*" StudyReview
  MultipleChoiceSession "1" *-- "0..*" MultipleChoiceQuestion
```

Solo sessions own their question state. A cached choice may depend on another card's current content. A Multiple-Choice snapshot retains its source ID after deletion. The physical ER shows its lack of a foreign key to the live card.

Sources [models](../../../backend/app/models.py), [cache](../../../backend/app/services/distractor_cache.py).

## Study Rooms

```mermaid
classDiagram
  class StudyRoom {
    str phase
    str mode
    str session_id
    int deck_owner_id
    bool share_private
  }
  class RoomMember {
    datetime joined_at
    datetime disconnected_at
    bool ready
    bool spectator
  }
  class RoomInvite {
    int sender_id
    datetime created_at
  }
  class RoomSession {
    dict players
    dict scores
    int position
    datetime deadline
    bool paused
  }
  class RoomQuestion {
    int position
    str fingerprint
    list options
    dict answers
  }
  class RoomMessage {
    dict author
    str text
  }
  User "0..1" -- "0..*" StudyRoom : host
  Deck "0..1" -- "0..*" StudyRoom : selected deck
  StudyRoom "1" *-- "0..6" RoomMember
  User "1" -- "0..*" RoomMember
  StudyRoom "1" *-- "0..*" RoomInvite
  User "1" -- "0..*" RoomInvite : invitee
  User "1" -- "0..*" RoomInvite : sender
  StudyRoom "1" *-- "0..*" RoomSession
  RoomSession "1" *-- "0..*" RoomQuestion
  Flashcard "0..1" -- "0..*" RoomQuestion : source
  StudyRoom "1" *-- "0..*" RoomMessage
  User "0..1" -- "0..*" RoomMessage : sender
```

Room membership models participant identity. The six-member maximum is a service constraint. A session belongs to one room, and the room's current-session pointer selects which session is active. Prepared questions contain answer data indexed by player identity in JSON.

Sources [models](../../../backend/app/models.py), [membership and limits](../../../backend/app/services/study_rooms.py).
