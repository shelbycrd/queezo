# 03 · Database design

[Architecture index](README.md) · [Physical ER diagrams](diagrams/database-er.md) · [Domain classes](diagrams/domain-classes.md)

The authoritative model declares 24 application tables. The schema records dates as naive UTC where appropriate and attaches the UTC offset when presenting timestamps. `activity_days.day` is a calendar date computed in Asia/Manila. Primary keys and unique constraints provide SQLite indexes in addition to explicit indexes described below.

## Physical table catalog

The table abbreviations PK and FK denote primary and foreign keys. Composite keys are grouped in parentheses.

| Table | PK and FKs | Storage and constraints |
| --- | --- | --- |
| `users` | `id`. Optional `featured_deck_id → decks.id` | Unique UID, case-insensitive username and email. Hash and profile fields. Featured deck clears on delete or loss of public eligibility. |
| `auth_sessions` | `token_hash`. `user_id → users.id` | SHA-256 token digest, creation and expiry. Indexes on user and expiry. |
| `login_throttles` | `key` | Time window and attempt count, indexed by `window_started`. Used by authentication and other operation budgets. |
| `session_presence` | `session_hash → auth_sessions.token_hash`, also PK | Latest heartbeat. Session deletion cascades. |
| `activity_days` | `(user_id, day)`. `user_id → users.id` | One record per account and local study date. |
| `friendships` | `(first_id, second_id)`. Both reference `users.id` | Canonical sorted pair. `requester_id` must be an endpoint of the pair; it is an integer, with no independent FK. Index on `second_id`. |
| `profile_avatar_changes` | `id`. `user_id → users.id` | Timestamp and composite user/time index support the change window. |
| `profile_reports` | `id`. `target_id` and `reporter_id → users.id` | Both relationship columns indexed. Target differs from reporter. Includes reason, explanation, and review time. |
| `decks` | `id`. Nullable `owner_id → users.id` | Indexed owner, unique share token, visibility and a 1–120 character title. Null owner supports preserved legacy data. |
| `flashcards` | `id`. `deck_id → decks.id` | Indexed deck, two-sided text, inline nullable raster photo data, timestamps. Database checks bound text at 10,000 characters. The insert trigger caps decks at 150 cards. |
| `flashcard_distractor_cache` | `flashcard_id → flashcards.id`, also PK | Exactly three JSON array entries, Front/Back fingerprint, model, generation version, source and timestamps. Source is `ollama` or `fallback`. |
| `flashcard_distractor_sources` | `(flashcard_id, position)`, with `flashcard_id → cache` and `source_card_id → flashcards.id` | Indexed source card, its fingerprint, and slot 0–2. Self-dependency disallowed. |
| `flashcard_distractor_jobs` | `flashcard_id → flashcards.id`, also PK | Temporary fenced lease token and expiry per card. |
| `study_sessions` | UUID `id`, `deck_id → decks.id` and optional `owner_id → users.id` | Indexed owner, deck, and state. Holds seeded order, current presentation state, counts, and timestamps. `current_card_id` is a logical pointer. |
| `study_session_cards` | `id`. `session_id → study_sessions.id` and nullable `flashcard_id → flashcards.id` | Indexed session and card. Unique initial order per session, text/photo snapshots and schedule state. Source deletion nulls the live pointer. |
| `study_reviews` | `id`. References `study_sessions.id` and `study_session_cards.id` | Indexed relationships. Unique presentation number and presentation token within each session. Difficulty in easy, normal, hard. |
| `multiple_choice_sessions` | UUID `id`. `owner_id → users.id` and `deck_id → decks.id` | Indexed deck, preparation and study timestamps, timing, status, optional hashed share grant. Active, preparing, failed, completed, and cancelled are stored states. |
| `multiple_choice_questions` | UUID `id`. `session_id → multiple_choice_sessions.id` | Unique position and original card ID per session. Indexed logical `source_card_id` added by baseline migration, with no FK to live cards. Options and correct ID form a pair. Failure excludes options. Submitted option and answer timestamp form a pair. |
| `study_rooms` | UUID `id` (internal) and unique uppercase 8-hex public `code`. Nullable `host_id → users.id` and `deck_id → decks.id` | Both FKs set null on deletion. `deck_owner_id` and current `session_id` are logical pointers. Phase and update time indexed. |
| `study_room_members` | `(room_id, user_id)`, references room and user | User index, join order, heartbeat/disconnect timestamps, ready and spectator flags. |
| `study_room_invites` | `(room_id, user_id)`, references room and invitee. `sender_id → users.id` | Indexed invitee. Lists sort by creation time. Sender membership and friendship are checked in service code. |
| `study_room_sessions` | UUID `id`. `room_id → study_rooms.id`, nullable `host_id → users.id` (starting host, set null on user deletion) | Indexed room and deadline. JSON roster and scores, question position, deadlines, pause and worker-claim state. |
| `study_room_questions` | `(session_id, position)`. `session_id → study_room_sessions.id`, nullable `card_id → flashcards.id` | Source deletion sets card ID to null. Stores fingerprint, question/options/photos, correct ID, failure flag, and JSON answers keyed by player ID. |
| `user_achievements` | `(user_id, achievement_key)`. `user_id → users.id`, cascade | Lazily created progress counter, nullable Manila `period_date` for daily achievements, nullable `unlocked_at`, `updated_at`. Definitions live in code. |
| `user_achievement_credits` | `(user_id, achievement_key, subject)`. `user_id → users.id`, cascade | One row per distinct subject already counted (Hoster: room ID). Added because room sessions could not tell distinct successful hosting apart. |
| `study_room_messages` | `id`. `room_id → study_rooms.id` and nullable `sender_id → users.id` | Both relationship columns indexed. Autoincrement message IDs, author snapshot, plain text, and creation time. User deletion can retain author snapshot with a null sender FK. |

Sources: [models and index declarations](../../backend/app/models.py), [baseline SQL migrations](../../backend/app/database.py), [profile trigger migration](../../backend/app/profile_migration.py).

## Ownership, integrity, and persistence

Owned reads filter by account ID and parent deck. Shared solo sessions are still bound to the initiating account and match the current share token digest and shareable visibility. Room access derives from membership, current visibility, and the room's private-deck grant. Cache rows are card-scoped, independent of user and session. Only authorized workflows read them.

Foreign keys are enabled per connection. WAL supports concurrent readers with a single writer. SQLite uses a 30-second busy timeout, and mutable read/modify/write flows take `BEGIN IMMEDIATE` before validating state. This encloses readiness and answer checks, scoring, and cache publication in consistent transactions. Workflow-specific read transactions produce consistent snapshots when multiple selects must agree. Inference and Argon2 work run outside long write transactions.

Owned deck deletion cascades into cards, the per-card cache and leases, and solo sessions. Deleting a single card preserves already prepared study snapshots. Classic and rooms null their live card reference. Solo Multiple-Choice retains its original card ID as an integer. Profile moderation, session revocation, and account deletion are deliberate operations through backend routes or CLI, with explicit service cleanup where FK rules alone do not express the desired outcome.

Sources: [connection and transaction setup](../../backend/app/database.py), [owner-scoped queries](../../backend/app/routers/decks.py), [share and session guards](../../backend/app/services/multiple_choice.py), [room grants](../../backend/app/services/study_rooms.py), [CLI](../../backend/app/cli.py).

## Schema evolution and recovery

`PRAGMA user_version` is 6. The Flashcards backend checks and migrates the database before accepting requests. A populated older file receives a verified pre-migration snapshot before the transaction applies schema changes. The baseline migration repairs legacy ownership, cards/media, sharing, profile fields, study columns, indexes, and triggers. Unsupported legacy card content must be repaired explicitly. The room schema was introduced by v2. V3 adds the card-lease table, backfills cache provenance labels, and adds the nullable hashed share grant to solo sessions. These changes preserve existing question snapshots and cache text. V5 adds `study_rooms.code` and backfills every existing room with a unique random code before creating the unique index. No rows are removed. V6 adds the achievement tables and `study_room_sessions.host_id`, then backfills Studious once from `completed` Classic and Multiple-Choice sessions: the earliest Manila day with ten completions unlocks it at the tenth completion time, otherwise today's count becomes today's progress. Deck Master and Hoster are not backfilled. Copied decks are indistinguishable from originals and deleted decks are gone, and past room sessions never recorded their starting host. The backfill runs before requests are accepted, so its history cannot be counted again.

Backup and recovery use SQLite's online backup API, integrity and foreign-key verification, configurable retention, and restore to a separate output with session revocation on the restored copy. See [deployment](07-deployment-and-infrastructure.md) for storage boundaries and [the runbook](../production/DATABASE_RELIABILITY.md) for recovery operations.

Sources: [database initialization](../../backend/app/database.py), [legacy repair](../../backend/app/migrate_cards.py), [SQLite backup operations](../../backend/app/sqlite_ops.py).
