# State machine · Shared distractor preparation

[Architecture index](../../README.md) · [Flashcards and AI](../../05-flashcards-and-ai.md)

```mermaid
stateDiagram-v2
  [*] --> Lookup : Authorized preparer requests current card
  Lookup --> Hit : Valid fingerprint, version, model dependency and provenance
  Lookup --> Waiting : Cache missing or stale
  Waiting --> Lookup : Another worker may have published choices
  Waiting --> Generating : Inference slot and fenced card lease acquired
  Generating --> Generating : Retry permitted within attempt budget
  Generating --> Filling : Fewer than three AI candidates
  Generating --> Publishing : Three valid AI candidates
  Filling --> Publishing : Three distinct choices available
  Filling --> Failed : Insufficient eligible choices
  Publishing --> Persisted : Lease, authorization and sources still valid
  Publishing --> Failed : Changed card or lost lease
  Generating --> Failed : Cancelled or outer preparation timeout
  Hit --> [*]
  Persisted --> [*]
  Failed --> [*]
```

These are workflow states. The database stores a valid result row and a separate expiring lease, without a distractor-status enum. Front/Back edits, deletion of a card or dependency, or incompatible generation identity make future lookups miss. Hard worker failure is bounded by lease expiry.

Sources [generation](../../../../backend/app/services/distractors.py), [lease, lookup, and publication](../../../../backend/app/services/distractor_cache.py), [invalidation triggers](../../../../backend/app/database.py).
