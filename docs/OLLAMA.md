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

## SQLite cache

Call `await get_or_generate_distractors(card_id, user)` from `app.services.distractor_cache` with the authenticated `User`. The service looks up an owner-scoped cache before calling Ollama. This scope also applies to publicly shared decks. Creating a flashcard does not generate choices.

When Ollama provides fewer than three valid choices, the service keeps them and randomly fills the remaining slots from distinct Back answers in the same deck. It excludes the current card and comparisons equivalent to its Back or a choice already selected. A deck can supply all three distractors while Ollama is offline if it has three other eligible answers. If the combined pool is too small, new preparations report the model's last outcome and save no incomplete cache entry. A usable response with too few distinct choices reports `insufficient_distractors`. Normalized text checks can catch exact equivalents, and both AI-generated and deck-derived answers can be ambiguous in context.

Each flashcard has at most one row in `flashcard_distractor_cache` with three choices, a SHA-256 fingerprint of its exact Front and Back text, the configured model tag, the generation version, and UTC timestamps. Startup adds `flashcard_distractor_sources` and its invalidation triggers to existing databases. Each deck-derived choice records its position, source card ID, and the source card’s Front/Back fingerprint. Positions without a source row are Ollama choices, including valid entries from before this migration.

Editing or deleting a target card clears its cache. Editing or deleting a source card clears only the caches that used its answer. These changes apply to future preparation, and saved questions keep their snapshots. A valid hybrid or deck-only cache stays eligible after Ollama becomes available again.

A model or generation-version mismatch causes a cache miss. Phase 3.2 uses generation version 2, so version 1 choices regenerate on demand and saved study snapshots are preserved. Bump `GENERATION_VERSION` in the generator when changing the prompt or validation rules, or when replacing a model without changing its tag. The service opens its own short transactions and runs inference between them. Call it before opening a write transaction for a study session. If a card is edited during generation, the service returns a 409 and the caller can try again. Deleted or inaccessible cards return a 404. When the combined choices fall short, the cache service raises `InsufficientDistractorsError`.

Concurrent requests for the same card on one event loop share a successful generation. Separate workers may generate in parallel on a miss. SQLite keeps a single matching row, and competing writers for the same content and settings reuse the first committed result.

The [multiple-choice study API](MULTIPLE_CHOICE.md) adds a preparation workflow, stores shuffled question snapshots, and grades submitted options against the original Back.
