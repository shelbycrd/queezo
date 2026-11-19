# Local Ollama distractor generation

Phase 1 adds a Python service that generates three incorrect choices for one flashcard. It takes the card’s Front and Back as text. The Back remains the correct answer.

## Configuration

Run Ollama on the Windows host and install the model with `ollama pull qwen3:1.7b` if it is missing. The backend container must be able to reach the host's Ollama API. [Ollama chat API](https://docs.ollama.com/api/chat)

| Variable | Docker Compose default |
| --- | --- |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` |
| `OLLAMA_MODEL` | `qwen3:1.7b` |

Set overrides in `.env` at the repository root. The base URL should point to a trusted Ollama server because the service sends it both sides of the card. When running Python directly on the Windows host, set `OLLAMA_BASE_URL` to `http://127.0.0.1:11434` in the Python process's environment. The normal backend startup and Classic Mode work without Ollama.

## Service behavior

Backend callers can use `await generate_distractors(front, back)` from `app.services.distractors`. The service asks for six candidates through `/api/chat` with JSON mode, `think=false`, and streaming disabled. It keeps valid candidates across attempts and samples three without replacement. Comparisons ignore whitespace and capitalization, which catches exact matches and duplicates. An ambiguous or partially correct distractor can still pass.

Each attempt has a 60-second deadline, with a five-second connection timeout. The service makes up to three attempts. It retries insufficient candidates, invalid responses, and temporary transport or HTTP errors. Configuration failures and permanent HTTP errors raise `DistractorGenerationError` immediately. If generation fails, the service raises that error without returning partial or invented choices.

## SQLite cache

Phase 2A adds `await get_or_generate_distractors(card_id, user)` from `app.services.distractor_cache`. Pass the authenticated `User`. The service uses the same owner-only card scope as flashcard CRUD, including for publicly shared decks and unassigned legacy cards. Creating a flashcard does not generate choices.

Backend startup creates the `flashcard_distractor_cache` table in place. Each flashcard has at most one row with three choices, a SHA-256 fingerprint of the exact Front and Back text, the configured model tag, the generation version, and UTC creation and update timestamps. Changing either text side removes its cache row. Deleting the card also deletes the row. Unchanged text and unrelated cards keep their entries.

A model or generation-version mismatch causes a cache miss. Bump `GENERATION_VERSION` in the generator when changing the prompt or validation rules, or when replacing a model without changing its tag. The service opens its own short transactions and runs inference between them. Call it before opening a write transaction for a study session. If a card is edited during generation, the service returns a 409 and the caller can try again. Deleted or inaccessible cards return a 404. Generation errors propagate without writing choices.

Concurrent requests for the same card on one event loop share a successful generation. Separate workers may generate in parallel on a miss. SQLite keeps a single matching row, and competing writers for the same content and settings reuse the first committed result.

The [multiple-choice study API](MULTIPLE_CHOICE.md) adds a preparation workflow, stores shuffled question snapshots, and grades submitted options against the original Back.
