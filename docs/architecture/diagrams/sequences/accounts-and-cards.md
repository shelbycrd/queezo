# Sequence diagrams · Accounts and card editing

[Architecture index](../../README.md) · [Security](../../04-authentication-and-security.md)

## Registration and login

```mermaid
sequenceDiagram
  actor Student
  participant Vue as AuthView / session.js
  participant API as Auth router and service
  participant DB as SQLite
  Student->>Vue: Enter account credentials
  Vue->>API: POST /api/auth/signup or /api/auth/login
  API->>API: Check origin, request limits and inputs
  API->>DB: Reserve auth budget in short write transaction
  alt Sign up and public signup permitted
    API->>API: Hash new password with Argon2id
    API->>DB: Atomically insert account and issue session
  else Login
    API->>DB: Read account and password-hash snapshot
    API->>API: Verify Argon2id outside write transaction
    API->>DB: Recheck account and issue session in short write transaction
  end
  alt Accepted
    API-->>Vue: HttpOnly cookie, safe identity and CSRF token
    Vue->>API: GET /api/auth/me during later bootstrap
    API->>DB: Validate token digest and expiry
    API-->>Vue: Current public-safe account projection and CSRF
  else Rejected
    API-->>Vue: Validation, conflict, credential or rate-limit response
  end
```

Database uniqueness is authoritative for concurrent signups. Login performs dummy verification when appropriate and checks the original hash before committing a session. The browser keeps CSRF in memory. The raw session secret travels in the cookie.

Sources [auth routes](../../../../backend/app/auth/router.py), [service](../../../../backend/app/auth/service.py), [frontend session](../../../../frontend/src/services/session.js).

## Deck and card creation

```mermaid
sequenceDiagram
  actor Owner
  participant Vue as Deck views
  participant API as Deck router
  participant DB as SQLite
  Owner->>Vue: Enter title and visibility
  Vue->>API: POST /api/decks with session cookie and CSRF
  API->>DB: Authorize account, check quota and insert deck
  API-->>Vue: Created owned deck
  Owner->>Vue: Provide Front, Back and optional photos
  Vue->>API: POST /api/decks/{deck_id}/cards
  API->>DB: Check owner and card quota in write transaction
  API->>API: Enforce text and raster constraints
  alt Valid
    API->>DB: Insert two-sided card
    API-->>Vue: Created card
  else Invalid or unauthorized
    API-->>Vue: Error response
  end
```

Deck creation defaults to private. Each new card is eligible for later inference, but creation has no inference dependency. Validation also runs at API schema boundaries.

Sources [owned deck routes](../../../../backend/app/routers/decks.py), [input schemas](../../../../backend/app/schemas.py), [image validation](../../../../backend/app/services/card_images.py).

## Edit and invalidate

```mermaid
sequenceDiagram
  actor Owner
  participant Vue as DeckView
  participant API as Deck router
  participant DB as SQLite and cache triggers
  Owner->>Vue: Save a card edit
  Vue->>API: PATCH /api/cards/{card_id}
  API->>DB: Verify ownership and write validated fields
  alt Front or Back text changed
    DB->>DB: Invalidate target and cache entries relying on this card
    DB->>DB: Cascade removed cache provenance
  else Same Front and Back
    DB->>DB: Keep cache identity
  end
  API-->>Vue: Updated card
  Note over DB: Prepared question snapshots remain unchanged
```

The trigger invalidates dependencies in the same committed write. A generator that started before the edit cannot publish the old choices because it rechecks the card fingerprint and lease.

Sources [card editing](../../../../backend/app/routers/decks.py), [triggers](../../../../backend/app/database.py), [cache publication](../../../../backend/app/services/distractor_cache.py).
