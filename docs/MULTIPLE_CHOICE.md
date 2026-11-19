# Multiple-choice study API

From a deck, choose **Study**, then **Multiple-Choice Mode**. The preparation screen tracks the opening questions and starts study automatically when the ordered threshold is reached. The rest of the deck can continue preparing while you study. A question is graded when the student selects **Check answer**, and the results use server-recorded totals. Open **Multiple-Choice history** on the deck to resume a saved session or view a summary. Refreshing resumes at the current unanswered question or summary. The grading response marks the correct answer and the student’s choice directly in the list.

Sessions are owner-only. Use the normal session cookie for every route and send the CSRF header on POST requests. Shared decks can be studied once copied into the student's own decks.

| Method and path | Result |
| --- | --- |
| `POST /api/decks/{deck_id}/multiple-choice` | **202** with the new session state. Optionally send `{"scope":"question","seconds":30}` or `{"scope":"deck","seconds":600}`. An empty deck returns **409**. |
| `GET /api/multiple-choice/{session_id}` | Current state and preparation progress. Poll while the `preparing` flag is true, including during active study. |
| `POST /api/multiple-choice/{session_id}/start` | **200** when the ordered readiness threshold is met. Idempotent for an active session. Returns **409** while the first questions are still preparing. |
| `POST /api/multiple-choice/{session_id}/retry` | **202** while a failed session prepares its unfinished cards again. A previously started session retries interrupted slots and resumes study from the saved position. |
| `POST /api/multiple-choice/{session_id}/continue` | **200** to resume a failed session with ready questions or finish a previously started session with no questions left. Skips the reported failures. |
| `POST /api/multiple-choice/{session_id}/cancel` | **200** with the cancelled state. Stops its preparation job and preserves any already saved cache entries and study results. |
| `GET /api/multiple-choice/{session_id}/question` | Current unanswered question with `id`, `front`, nullable `front_image`, and four shuffled `options` containing only `id` and `text`. Returns **409** while the next position is still preparing. |
| `POST /api/multiple-choice/{session_id}/question` | Opens or resumes the current timed question. Returns `session`, `question`, and `remaining_ms`. A waiting or completed session returns a null question. An existing deck countdown can continue while waiting. |
| `POST /api/multiple-choice/{session_id}/answer` | Takes `{"question_id":"…","option_id":"…"}`. Returns `question_id`, `selected_option_id`, `is_correct`, `correct_option` with its ID and original Back text, nullable `back_image`, and the updated `session` state. |
| `GET /api/decks/{deck_id}/multiple-choice/sessions` | Up to 50 recent multiple-choice sessions for the deck, newest first. |

Missing or inaccessible decks and sessions return **404**. An illegal transition, repeated answer, or question ID that is no longer current returns **409**. An option ID outside the current question or unexpected answer fields return **422**. Actions on an expired session return **410**.

## Timed sessions

The server starts the clock when the first ready question is opened. A question limit resets for each new question. A deck limit keeps running between questions and during feedback. Both limits continue while the page is closed or refreshed. The server rejects late answers. A per-question countdown begins when that question opens. A deck timeout stops pending preparation before completing and counts remaining ready questions as missed. Timed session responses include the timing settings and a `timed_out` count. Existing unlimited sessions continue using the question GET route.

## Preparation and session lifecycle

The response includes the session and deck IDs, `deck_title`, `mode: "multiple_choice"`, `status`, `answered`, `correct`, `created_at`, `expires_at`, and nullable `finished_at`. `opening` reports the resolved prefix’s playable count and target, `can_start` signals the client to start study automatically, `study_started` persists that decision, and `question_ready` signals whether the next unanswered position is playable. Preparation progress includes:

```json
{
  "progress": {"total": 3, "completed": 3, "ready": 2, "failed": 1},
  "failures": [{"card_id": 42, "reason": "insufficient_distractors"}]
}
```

- A session starts in `preparing`. It stores a single shuffled sequence. The cache pass may prepare cached snapshots anywhere in the sequence. Misses go to Ollama and same-deck fallback in position order. The first five playable questions in the resolved prefix fill the opening progress bar and trigger study. Shorter decks settle every position first.
- Starting study sets the state to `active` while preparation continues. Students wait at an unresolved position and advance past permanent failures once resolved. If preparation settles before study begins, a partial session offers Retry or Continue. An interrupted started session also offers recovery, and Retry preserves earlier permanent skips. The `insufficient_distractors` reason means Ollama and the same-deck answers together supplied fewer than three distinct distractors for that card. Repeated Back answers count once, and the current Back is excluded. If the fallback still cannot fill the slots, the latest model attempt can also determine the failure reason. The API reports `ollama_unavailable` for connection or service failures, `generation_timeout` when the model request times out, and `invalid_ai_response` for malformed output. Older session snapshots may still show `generation_failed`. Other reasons include `card_changed`, `card_missing`, `preparation_timeout`, `interrupted`, or `preparation_failed`. Retry, continue with the ready subset, or return to Classic. A deleted source card stays in the failure report. Start a fresh session to use current deck membership.
- Each ready question is a snapshot. Edits or deletions after preparation leave that question and its correct answer intact. Question IDs, option IDs, and option order stay stable across requests. Grading compares the submitted option ID to the stored correct option ID and records one answer per question.
- Completion requires settled preparation and consumption of every ready question, by an answer or the applicable study timer. Each accepted answer counts toward study activity. The deck's multiple-choice history is separate from its Classic history. Deleting a deck removes its sessions and their questions.
- Preparation has a 15-minute deadline per attempt, including time waiting for Ollama. Active, preparing, and retryable sessions expire 24 hours after creation. Cancelled and completed sessions remain in history. On restart, unfinished preparation is marked retryable, and already prepared questions are retained.

The preparation coordinator is scoped to the backend's current single-worker Docker configuration. See [the progressive benchmark](quality/PROGRESSIVE_STUDY.md) for time-to-playable measurements. AI and same-deck distractors can both be contextually valid or ambiguous. Grading always uses the original Back.
