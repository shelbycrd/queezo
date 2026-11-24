# Activity diagrams · Multiple-Choice preparation

[Architecture index](../../README.md) · [Flashcards and AI](../../05-flashcards-and-ai.md)

## Multiple-Choice preparation

![Ordered Multiple-Choice preparation](../rendered/multiple-choice-preparation.svg)

```plantuml
@startuml
start
:Validate account, deck grant and session budget;
if (Request admissible?) then (yes)
  :Persist session and randomized positions;
else (no)
  :Return authorization or capacity error;
  stop
endif
:Schedule bounded preparation;
:Batch-read caches and save valid cached snapshots;
while (Unsettled position and current job?) is (yes)
  :Select next position by assigned order;
  :Resolve shared cache or generation;
  if (Valid choices and current source?) then (yes)
    :Snapshot four shuffled choices with stable IDs;
  else (no)
    :Record preparation failure;
  endif
endwhile (no)
:Settle remaining job state when appropriate;
stop
@enduml
```

Batch cache reads and early writes reduce repeated lookups. The queue carries session and attempt identities. Stale or cancelled jobs cannot publish into a newer attempt. A snapshot owns its option IDs even after the source is edited.

Sources [preparation API](../../../../backend/app/routers/multiple_choice.py), [worker and cache batch](../../../../backend/app/services/multiple_choice.py).

## Progressive question loading

![Progressive question loading and recovery](../rendered/progressive-question-loading.svg)

```plantuml
@startuml
start
:Poll session readiness after route load;
while (Preparing and cannot start?) is (yes)
  :Display ordered opening progress;
  :Fetch latest status;
endwhile (no)
if (Start allowed or already started?) then (yes)
  :Start or resume the same saved session;
else (no)
  :Offer allowed recovery actions;
  stop
endif
while (Study active?) is (yes)
  :Read least unresolved playable or pending position;
  if (Question snapshot available?) then (yes)
    :Open with server deadline if timed;
    :Submit or time out, then advance after feedback;
  else (no)
    :Wait for preparation without reordering;
    :Poll latest session state;
  endif
endwhile (no)
:Render terminal state or result;
stop
@enduml
```

Opening progress counts up to five ready questions in order, skipping permanent failures and stopping at the first pending position. The backend distinguishes terminal preparation failures from pending positions and preserves the order of playable questions. Cancellation, retry, and continue depend on session state. Results do not appear until preparation and eligible answers settle.

Sources [status and next question](../../../../backend/app/services/multiple_choice.py), [progressive view](../../../../frontend/src/views/MultipleChoiceView.vue).

## Shared cache lookup and generation

![Shared cache lookup, claim and generation](../rendered/shared-cache-lookup.svg)

```plantuml
@startuml
start
:Read authorized card and shared cache;
if (Cache valid?) then (yes)
  :Return three choices immediately;
  stop
endif
while (No matching cache or owned lease?) is (wait)
  :Wait for local slot, recheck and attempt SQLite claim;
  if (Another worker still owns a lease?) then (yes)
    :Release local slot and poll within deadline;
  endif
endwhile (resolved)
if (Matching result available?) then (yes)
  :Reuse existing result;
else (lease owned)
  :Generate candidates within attempt and time budgets;
  :Publish only after validating lease and current source;
endif
:Return valid choices or typed failure;
stop
@enduml
```

The cache is shared by the solo and room paths and is keyed by the underlying flashcard. A normal cache hit does not acquire the model slot. Local serialization is separate from the per-card lease in SQLite. The surrounding job can cancel or time out during a wait.

Source [cache lookup and claim](../../../../backend/app/services/distractor_cache.py).

## AI failure and deck fallback

![AI failure and deck-answer fallback](../rendered/ai-and-fallback.svg)

```plantuml
@startuml
start
:Collect normalized valid AI candidates across bounded attempts;
if (Three AI choices available?) then (yes)
  :Select three AI choices;
else (no)
  :Keep accepted partial candidates;
  :Read different Back answers from current deck;
  :Filter blanks, duplicate values and original correct Back;
  if (Enough combined candidates?) then (yes)
    :Fill missing slots and retain source card provenance;
  else (no)
    :Report insufficient distractors;
    stop
  endif
endif
:Revalidate fingerprint and fenced claim;
if (Publication still valid?) then (yes)
  :Persist three choices and source slots;
else (no)
  :Reject stale publication;
endif
stop
@enduml
```

Fallback is triggered by insufficient accepted candidates, including recoverable model errors. It uses existing Back values. Both shared-cache consumers continue to use the source card's own Back as the one correct choice.

Sources [candidate validation](../../../../backend/app/services/distractors.py), [fallback and save transaction](../../../../backend/app/services/distractor_cache.py).
