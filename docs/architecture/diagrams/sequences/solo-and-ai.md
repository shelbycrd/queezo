# Sequence diagrams · Solo study and AI

[Architecture index](../../README.md) · [Flashcards and AI](../../05-flashcards-and-ai.md)

## Solo session initialization

```mermaid
sequenceDiagram
  actor Student
  participant Vue as StudyOptions / MultipleChoiceView
  participant API as Multiple-Choice API
  participant Worker as PreparationJobs
  participant DB as SQLite
  Student->>Vue: Start Multiple-Choice
  Vue->>API: POST owned or shared Multiple-Choice route
  API->>DB: Validate owner or current share grant and quota
  API->>DB: Save session and one shuffled sequence of positions
  API->>Worker: Schedule bounded preparation
  API-->>Vue: 202 and session ID
  Worker->>DB: Batch-read eligible cached distractors
  Worker->>DB: Publish cached snapshots at assigned positions
  par Prepare remaining positions
    loop Each uncached position in assigned order
      Worker->>DB: Resolve choices and save snapshot or failure
    end
  and Poll opening progress
    Vue->>API: GET /api/multiple-choice/{session_id}
    API->>DB: Read ordered readiness
    API-->>Vue: Progress and can_start
  end
  Vue->>API: POST session /start when allowed
  API->>DB: Persist study start once
  Vue->>API: POST session /question to open current position
  API-->>Vue: Question, options and optional deadline
```

Progress polling and question opening are distinct. Published cache hits may occupy later positions. They do not change the ordered opening threshold or the question the learner receives. Preparation can continue during study.

Sources [MCQ routes](../../../../backend/app/routers/multiple_choice.py), [preparation and projections](../../../../backend/app/services/multiple_choice.py), [Vue view](../../../../frontend/src/views/MultipleChoiceView.vue).

## Generation and persistence

```mermaid
sequenceDiagram
  participant Prep as Solo or room preparer
  participant Cache as distractor_cache
  participant AI as distractors
  participant Model as Ollama
  participant DB as SQLite
  Prep->>Cache: Resolve choices with card and owner context
  Cache->>DB: Check current fingerprint and cache
  Cache->>Cache: Wait for local inference slot
  Cache->>DB: Recheck and claim per-card fenced lease on miss
  alt Cache filled by another worker
    DB-->>Cache: Valid existing choices
  else Lease obtained
    Cache->>AI: Generate and retain valid candidates
    loop Initial request and up to two appropriate retries
      AI->>Model: POST /api/chat with JSON mode and think=false
      Model-->>AI: Candidate envelope or error
      AI->>AI: Parse and compare normalized candidates
    end
    AI-->>Cache: Three choices or error with partial candidates
    Cache->>DB: Recheck ownership, fingerprint and lease in write transaction
    Cache->>DB: Fill remaining slots if needed and publish valid choices
    Cache->>DB: Release claim
  end
  Cache-->>Prep: Choices or preparation error
```

The initial structured request targets six candidates. The retry policy can vary candidate count and instructions. A running inference request does not hold the SQLite write transaction. Publication is fenced against stale workers.

Sources [Ollama generator](../../../../backend/app/services/distractors.py), [cache and fenced claims](../../../../backend/app/services/distractor_cache.py).

## Cache hit and fallback

```mermaid
sequenceDiagram
  participant Prep as Authorized preparer
  participant Cache as distractor_cache
  participant DB as SQLite
  participant AI as distractor generator
  Prep->>Cache: Read or generate for current card
  Cache->>DB: Inspect target, version, model dependency and provenance
  alt Three valid cached choices
    Cache-->>Prep: Return cached choices without model call
  else Missing or stale
    Cache->>AI: Run bounded generation under lease
    AI-->>Cache: Valid candidates, possibly partial
    alt Fewer than three valid AI choices
      Cache->>DB: Select distinct eligible Back values within same deck
    end
    alt Three valid combined choices and current lease
      Cache->>DB: Store choices and fallback source slots
      Cache-->>Prep: Return three choices
    else Insufficient choices or stale source
      Cache-->>Prep: Typed failure without publishing invalid cache
    end
  end
  Prep->>Prep: Build stable shuffled options using original Back
```

A pure deck-derived cache survives a model change. Mixed choices depend on the current model and the recorded fallback sources. Normalized text checks cannot establish semantic correctness.

Sources [cache rules and fallback](../../../../backend/app/services/distractor_cache.py), [solo consumer](../../../../backend/app/services/multiple_choice.py), [room consumer](../../../../backend/app/services/room_study.py).
