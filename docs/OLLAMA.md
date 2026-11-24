# Local Ollama distractor generation

Queezo asks a local Ollama model for distractors in Multiple-Choice Mode. Each question uses the flashcard’s original Back as its sole grading answer.

## Configuration

Run Ollama on the Windows host and install the model with `ollama pull qwen3:1.7b` if it is missing. The backend container must be able to reach the host's Ollama API. [Ollama chat API](https://docs.ollama.com/api/chat)

| Variable | Docker Compose default |
| --- | --- |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` |
| `OLLAMA_MODEL` | `qwen3:1.7b` |

Set overrides in `.env` at the repository root. The base URL should point to a trusted Ollama server because the service sends it both sides of the card. When running Python directly on the Windows host, set `OLLAMA_BASE_URL` to `http://127.0.0.1:11434` in the Python process's environment. The normal backend startup and Classic Mode work without Ollama.

## Service behavior

Backend callers can use `await generate_distractors(front, back)` from `app.services.distractors`. The service asks for six candidates through `/api/chat` with JSON mode, `think=false`, and streaming disabled. It keeps valid candidates across attempts and samples three without replacement. Each retry specifies the remaining count and includes the previous outcome, cumulative rejection counts, and examples of rejected choices. Every attempt excludes the original Back and earlier choices. Comparisons collapse whitespace and ignore capitalization to catch matches and duplicates. An ambiguous or partially correct distractor can still pass.

Format-based retries are limited to short, bare lowercase Latin input with keyboard patterns on both sides, or a three-consonant Back paired with a keyboard-pattern Front. These retries ask for similar literal strings, and choices must use lowercase Latin letters within one character of the Back's length. Failed conceptual attempts alone cannot switch modes. Ambiguous terms, names, longer text, and conventional code or identifier formats stay in conceptual mode.

Each attempt has a 60-second deadline, with a five-second connection timeout. The service makes at most three attempts. It retries insufficient candidates, invalid responses, and transient request failures. A failed connection, invalid configuration, or permanent HTTP rejection stops that card's attempts early. If Ollama falls short, `DistractorGenerationError.candidates` carries any validated candidates already collected.

## Shared SQLite cache

Owned-deck solo study, signed-in practice from a public or unlisted share link, and Study Rooms use the same cache. Each flashcard ID has at most one stored entry, independent of who studies it. A saved copy has new card IDs. Creating a card never calls Ollama.

The cache stores three plain-text choices in a SQLite JSON array, the exact Front/Back SHA-256 fingerprint, the model tag, generation version, source, and timestamps.

`source = ollama` means all three choices came from the model. `source = fallback` means one or more choices came from other cards in the same deck. The positional rows in `flashcard_distractor_sources` identify those source cards and their fingerprints. Hybrid results preserve valid model choices and fill the remaining slots from the deck.

The exact Front and Back and the normalized choices are checked before reuse. Edits or deletions invalidate the target and relevant provenance dependencies. Adding a card leaves valid choices intact. Deck names and visibility do not change cached choices. Visibility and the current share token control access independently.

A generation-version change invalidates all prior versions on demand. A model-tag change invalidates entries that contain model choices. A fully deck-derived entry stays valid across model changes. Model outages and later recovery do not replace valid cached fallback choices. Text comparison does not establish whether a distractor is semantically correct in context.

The `flashcard_distractor_jobs` table gives each card an expiring generation lease across workers. A claim is available only after the process has obtained its existing model slot. Waiters reuse a committed entry. The job identity fences stale writers, the provider deadlines bound inference, and expiry allows recovery after a hard crash. Cache publication and lease removal commit together. SQLite write transactions stay outside inference.

Schema v3 adds the lease table, backfills the source flag from existing provenance, and adds a hashed share-access field to solo sessions. The normal startup migration takes a verified backup before upgrading an existing database. Existing cached text, flashcards, and study snapshots are retained.

Shared solo practice requires a signed-in account and a valid share link. The app keeps session state for refresh and retry for up to 24 hours. It is excluded from Previous Session and study streaks. Expired shared sessions are removed when that account next starts Multiple-Choice.

For a deliberately targeted refresh, an operator can clear one card’s choices. This preserves saved questions and leaves the next authorized session to fill the cache.

```powershell
docker compose exec backend python -m app.cli clear-distractors --card-id 42
```

See [Multiple-Choice study](MULTIPLE_CHOICE.md) and [shared-cache verification](quality/SHARED_DISTRACTORS.md).
