# Multiple-choice study API

From a deck, choose **Study**, then **Multiple-Choice Mode**. The preparation screen shows progress and recovery options. A question is graded when the student selects **Check answer**, and the results use server-recorded totals. Open **Multiple-Choice history** on the deck to resume a saved session or view a summary. Refreshing resumes at the current unanswered question or summary. Feedback for an answer that was already submitted is shown only when the browser receives the grading response.

Phase 2B adds owner-only backend sessions. Use the normal session cookie for every route and send the CSRF header on POST requests. Shared decks can be studied once copied into the student's own decks.

| Method and path | Result |
| --- | --- |
| `POST /api/decks/{deck_id}/multiple-choice` | **202** with the new session state. An empty deck returns **409**. |
| `GET /api/multiple-choice/{session_id}` | Current state and preparation progress. Poll while the state is `preparing`. |
| `POST /api/multiple-choice/{session_id}/retry` | **202** while a failed session prepares its unfinished cards again. Ready snapshots stay in place. |
| `POST /api/multiple-choice/{session_id}/continue` | **200** with the active state. Requires a failed session with at least one ready question. Skips the reported failures. |
| `POST /api/multiple-choice/{session_id}/cancel` | **200** with the cancelled state. Stops its preparation job and preserves any already saved cache entries and study results. |
| `GET /api/multiple-choice/{session_id}/question` | Current unanswered question with `id`, `front`, nullable `front_image`, and four shuffled `options` containing only `id` and `text`. |
| `POST /api/multiple-choice/{session_id}/answer` | Takes `{"question_id":"…","option_id":"…"}`. Returns `question_id`, `selected_option_id`, `is_correct`, `correct_option` with its ID and original Back text, nullable `back_image`, and the updated `session` state. |
| `GET /api/decks/{deck_id}/multiple-choice/sessions` | Up to 50 recent multiple-choice sessions for the deck, newest first. |

Missing or inaccessible decks and sessions return **404**. An illegal transition, repeated answer, or question ID that is no longer current returns **409**. An option ID outside the current question or unexpected answer fields return **422**. Actions on an expired session return **410**.

## Preparation and session lifecycle

The response includes the session and deck IDs, `deck_title`, `mode: "multiple_choice"`, `status`, `answered`, `correct`, `created_at`, `expires_at`, and nullable `finished_at`. Preparation progress includes:

```json
{
  "progress": {"total": 3, "completed": 3, "ready": 2, "failed": 1},
  "failures": [{"card_id": 42, "reason": "generation_failed"}]
}
```

- A session starts in `preparing`. Completed preparation counts include ready and failed cards. Preparation reuses the [SQLite distractor cache](OLLAMA.md), and the backend permits one card generation at a time across sessions.
- Once all cards are ready, the state becomes `active`. If any fail, the state becomes `failed`. Reasons include `generation_failed`, `card_changed`, `card_missing`, `preparation_timeout`, `interrupted`, or `preparation_failed`. Retry, continue with the ready subset, or return to Classic. A deleted source card stays in the failure report. Start a fresh session to use current deck membership.
- Each ready question is a snapshot. Edits or deletions after preparation leave that question and its correct answer intact. Question IDs, option IDs, and option order stay stable across requests. Grading compares the submitted option ID to the stored correct option ID and records one answer per question.
- After the last answer the session is `completed`. Each accepted answer counts toward study activity. The deck's multiple-choice history is separate from its Classic history. Deleting a deck removes its sessions and their questions.
- Preparation has a 15-minute deadline per attempt, including time waiting for Ollama. Active, preparing, and retryable sessions expire 24 hours after creation. Cancelled and completed sessions remain in history. On restart, unfinished preparation is marked retryable, and already prepared questions are retained.

The preparation coordinator is scoped to the backend's current single-worker Docker configuration. AI distractors can still be ambiguous even after string validation.
