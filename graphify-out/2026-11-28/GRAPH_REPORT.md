# Graph Report - Queezo  (2026-11-27)

## Corpus Check
- 272 files · ~341,089 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 29 file(s) not represented in the graph (top: .css 10, .csv 9, (none) 4)

## Summary
- 2855 nodes · 7958 edges · 153 communities (116 shown, 37 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 782 edges (avg confidence: 0.91)
- Token cost: 672,320 input · 0 output

## Graph Freshness
- Built from commit: `c5515a57`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- DashboardView.vue
- utcnow
- User
- Frontend API Client
- Shared Request Handlers
- App.vue
- Database Schema Docs
- Study Room API
- Room View UI
- Flashcard
- Multiple-Choice Tests
- Multiple-Choice UI
- Phase 4B.1 Multiple-Choice performance
- Deck Library UI
- JSON Card Import
- test_study_rooms.py
- Distractor Cache Tests
- Rendered Architecture Diagrams
- test_schedule.py
- StudyView.vue
- Audio And Room Chat
- Queezo README
- app/main.py
- Distractor Cache
- Deck Editor UI
- Frontend Entry And Styles
- benchmark_performance.py
- admin_cli.py
- ScheduleSubjectDialog.vue
- Distractor Generator Tests
- room_study.py
- HomeSchedule.vue
- Profile Settings
- models.py
- ScheduleTimePicker.vue
- Study API Tests
- Friends Drawer
- app/schemas.py
- SharedStudyView.vue
- ProfileView.vue
- services/activity.py
- Compose.Backup Group
- Pomodoro Core Group
- create_user
- distractors.py
- Compose.Dev Group
- Components Group
- vue-router
- Profileabout Group
- test_auth.py
- Test Sharing Group
- evaluate.py
- ref_node_assert
- ScheduleActions.vue
- test_admin_console.py
- multipleChoiceSession
- utcnow
- test_achievements.py
- test_profiles.py
- PomodoroView.vue
- main
- Test Scheduler Group
- admin.py
- ScheduleView.vue
- services/study_rooms.py
- Gwaview Group
- friends.py
- measure
- Compose Group
- pomodoro.js
- Components Group
- Compose Group
- Deployment Group
- Compose Group
- Compose Group
- 01 System Overview Group
- Room joining and invitation validation
- Cat Group
- Profileachievements Group
- study.py
- test_password_management.py
- Test Card Import Group
- Study Rooms Group
- test_ownership_migration.py
- init_database
- pytest
- Compose Group
- Distractors Group
- Study Rooms Group
- Pomodoro Group
- test_gwa.py
- Compose Group
- test_sharing.py
- Container Architecture Group
- Flashcards Group
- test_crud.py
- Browser Components Group
- Study Rooms Group
- System Context Group
- Gwa Calculator Group
- Readme Group
- cli.py
- Progressive Question Loading Group
- Room Joining Group
- Queezo production readiness audit
- admin_auth.py
- Multiplayer Study Rooms
- Compose Overlays Group
- Study Rooms Group
- Study Rooms Group
- argparse
- Auth Implementation Group
- Auth Implementation Group
- Auth Implementation Group
- Browser Components Group
- Solo And Ai Group
- schedule.js
- SegmentedSwitch.vue
- Database Er Group
- Backend Components Group
- Compose Overlays Group
- Multiple Choice Group
- Study Rooms Group
- Queezo Cloud Group
- Readme Group
- Readme Group
- Verification Group
- Shared distractor verification
- Base
- H5 Ollama serial slot / admission queue
- Moderation commands (suspend, unpublish, changepassword, close room)

## God Nodes (most connected - your core abstractions)
1. `User` - 152 edges
2. `utcnow()` - 121 edges
3. `deck()` - 111 edges
4. `api()` - 89 edges
5. `Deck` - 81 edges
6. `Flashcard` - 77 edges
7. `showNotice()` - 71 edges
8. `vue` - 53 edges
9. `init_database()` - 49 edges
10. `active()` - 47 edges

## Surprising Connections (you probably didn't know these)
- `traced_lookup()` --calls--> `lookup()`  [INFERRED]
  docs/quality/benchmark_performance.py → backend/tests/test_distractor_cache.py
- `Graphify skill trigger` --semantically_similar_to--> `Graphify usage rules`  [INFERRED] [semantically similar]
  .claude/CLAUDE.md → AGENTS.md
- `Profile visibility (Public/Unlisted/Private)` --semantically_similar_to--> `Deck visibility (Private/Public/Unlisted)`  [INFERRED] [semantically similar]
  docs/PROFILES.md → README.md
- `Queezo AI project context` --semantically_similar_to--> `Queezo apps: Flashcards, GWA, Pomodoro`  [INFERRED] [semantically similar]
  docs/PROJECT_CONTEXT.md → AGENTS.md
- `measure()` --uses--> `MultipleChoiceQuestion`  [INFERRED]
  docs/quality/benchmark_performance.py → backend/app/models.py

## Import Cycles
- 2-file cycle: `backend/app/database.py -> backend/app/models.py -> backend/app/database.py`

## Hyperedges (group relationships)
- **Authentication security model** — auth_implementation_argon2id_hashing, auth_implementation_opaque_session_token, auth_implementation_csrf_tokens, auth_implementation_rate_limits [EXTRACTED 1.00]
- **Browser to Nginx to backend to SQLite** — docs_architecture_diagrams_rendered_base_compose_browser, docs_architecture_diagrams_rendered_base_compose_nginx, docs_architecture_diagrams_rendered_base_compose_backend, docs_architecture_diagrams_rendered_base_compose_volume [EXTRACTED 1.00]
- **Distractor generation pipeline** — docs_architecture_diagrams_components_mc, docs_architecture_diagrams_components_engine, docs_architecture_diagrams_components_cache, docs_architecture_diagrams_components_ai, docs_architecture_diagrams_components_ollama [EXTRACTED 1.00]
- **Browser to API request path** — docs_architecture_diagrams_container_architecture_browser, docs_architecture_diagrams_container_architecture_nginx, docs_architecture_diagrams_container_architecture_api, docs_architecture_diagrams_container_architecture_db [EXTRACTED 1.00]
- **Backup overlay flow** — docs_architecture_diagrams_deployment_backup, docs_architecture_diagrams_deployment_data, docs_architecture_diagrams_deployment_backups, docs_architecture_diagrams_deployment_restic [EXTRACTED 1.00]
- **Distractor preparation flow** — docs_architecture_05_flashcards_and_ai_solo_multiple_choice, docs_architecture_02_architecture_and_components_room_engine, docs_architecture_05_flashcards_and_ai_shared_distractor_cache, docs_architecture_05_flashcards_and_ai_same_deck_fallback, docs_architecture_01_system_overview_ollama [EXTRACTED 1.00]
- **Database backup, restore and migration recovery** — docs_production_database_reliability_backup_sidecar, docs_production_database_reliability_restic, docs_production_database_reliability_restore_to_separate_file, docs_production_database_reliability_versioned_migration [EXTRACTED 1.00]
- **Multiple-Choice distractor pipeline** — docs_multiple_choice_progressive_preparation, docs_ollama_distractor_generation, docs_ollama_shared_distractor_cache, docs_ollama_same_deck_fallback, docs_ollama_generation_lease [EXTRACTED 1.00]
- **MCQ preparation phases 4B.1-4B.3** — docs_quality_performance_doc, docs_quality_cache_first_doc, docs_quality_progressive_study_doc [EXTRACTED 1.00]
- **Shared distractor cache and generation flow** — docs_architecture_diagrams_rendered_multiple_choice_preparation_resolve_cache, docs_architecture_diagrams_rendered_room_gameplay_prepare_options, docs_architecture_diagrams_rendered_shared_cache_lookup_read_cache, docs_architecture_diagrams_rendered_ai_and_fallback_ai_candidates [INFERRED 0.85]
- **Distractor quality evaluation** — docs_quality_readme_evaluation_arms, docs_quality_findings_hybrid_policy, docs_quality_review_rubric_per_choice_ratings [INFERRED 0.85]
- **login_throttles operation budgets** — docs_architecture_03_database_design_login_throttles, docs_architecture_02_architecture_and_components_json_card_import, docs_architecture_06_multiplayer_study_rooms_invitation_rate_limit, docs_architecture_04_authentication_and_security_password_change [INFERRED 0.85]

## Communities (153 total, 37 thin omitted)

### Community 0 - "DashboardView.vue"
Cohesion: 0.08
Nodes (23): greeting(), sortFriends(), applied, clearSearch(), {data, error}, days, decks, friends (+15 more)

### Community 1 - "utcnow"
Cohesion: 0.06
Nodes (73): MultipleChoiceQuestion, MultipleChoiceSession, utcnow(), answer(), begin_study(), cancel(), continue_ready(), history() (+65 more)

### Community 2 - "User"
Cohesion: 0.12
Nodes (27): Deck, ProfileAvatarChange, User, avatar_times(), discover(), featured_options(), list_profile_decks(), name_date() (+19 more)

### Community 3 - "Frontend API Client"
Cohesion: 0.10
Nodes (34): ApiError, authenticatedUser(), authVersion(), csrfToken(), handleUnauthorized(), onUnauthorized(), setAuthenticatedUser(), unauthorized() (+26 more)

### Community 4 - "Shared Request Handlers"
Cohesion: 0.09
Nodes (48): api(), submit(), refresh(), respond(), send(), save(), loadOptions(), save() (+40 more)

### Community 5 - "App.vue"
Cohesion: 0.06
Nodes (40): dependencies, vue@3.5.46, vue-router@^4.6.0, accountMenu, auth, back, inviteCount, joinedRoomCount (+32 more)

### Community 6 - "Database Schema Docs"
Cohesion: 0.06
Nodes (50): activity_days, auth_sessions, decks, flashcard_distractor_cache, flashcard_distractor_jobs, flashcard_distractor_sources, flashcards, friendships (+42 more)

### Community 7 - "Study Room API"
Cohesion: 0.12
Nodes (40): answer(), AnswerInput, chat(), ChatInput, consistent_read(), create(), InvitationResponse, invite() (+32 more)

### Community 8 - "Room View UI"
Cohesion: 0.04
Nodes (69): Challenge scoring by elapsed time, Collaborative mode with host pause, Five-second review, Collaborative and Challenge gameplay, inviteToStudy(), apply(), connect(), data (+61 more)

### Community 9 - "Flashcard"
Cohesion: 0.25
Nodes (20): Flashcard, add_card(), create_deck(), dashboard(), delete_card(), delete_deck(), edit_card(), get_card() (+12 more)

### Community 10 - "Multiple-Choice Tests"
Cohesion: 0.11
Nodes (36): mc(), mock_generation(), stage_progressive_prefix(), start(), test_additive_upgrade_preserves_classic_history_and_deck_deletion_cascades(), test_boot_recovery_marks_unfinished_preparations_retryable(), test_cache_hit_shuffled_options_and_grading_survive_source_edits(), test_cache_pass_queues_invalid_entries_for_generation() (+28 more)

### Community 11 - "Multiple-Choice UI"
Cohesion: 0.05
Nodes (36): scoreSummary(), chooseSharedStudy(), accountVersion, {active}, again(), choosing, clock, clockLabel (+28 more)

### Community 12 - "Phase 4B.1 Multiple-Choice performance"
Cohesion: 0.17
Nodes (11): Phase 4B.2 Cache-first scheduling, Phase 4A findings, AI-first hybrid fallback policy, Lone surrogate Unicode defect and fix, Cold/warm/hybrid/two-session benchmark scenarios, Phase 4B.1 Multiple-Choice performance, Phase 4B.3 Progressive Multiple-Choice study, Multiple-Choice distractor QA (+3 more)

### Community 13 - "Deck Library UI"
Cohesion: 0.07
Nodes (29): icon(), paths, color, emit, pending, props, study(), target (+21 more)

### Community 14 - "JSON Card Import"
Cohesion: 0.07
Nodes (37): {active}, chooseFile(), {deckId, count}, dialog, dragging, drop(), edited(), emit (+29 more)

### Community 15 - "test_study_rooms.py"
Cohesion: 0.17
Nodes (32): InsufficientDistractorsError, answer_for(), configure_room(), join(), make_room(), make_users(), sign_in(), test_challenge_timer_clamps_late_answers_and_ranks_by_points() (+24 more)

### Community 16 - "Distractor Cache Tests"
Cohesion: 0.19
Nodes (35): deck(), cached_rows(), lookup(), make_card(), source_rows(), test_ai_and_deck_choices_are_cached_with_source_provenance(), generate_mocked(), respond() (+27 more)

### Community 17 - "Rendered Architecture Diagrams"
Cohesion: 0.06
Nodes (40): Collect normalized AI candidates, Filter blanks/duplicates/correct Back, Report insufficient distractors, Persist three choices and source slots, Reject stale publication, Revalidate fingerprint and fenced claim, Read Back answers from current deck, backend app.main (+32 more)

### Community 18 - "test_schedule.py"
Cohesion: 0.07
Nodes (60): ScheduleArchive, ScheduleMeeting, ScheduleSetting, ScheduleSubject, community(), read_shared(), shared_view(), clear_schedule() (+52 more)

### Community 19 - "StudyView.vue"
Cohesion: 0.06
Nodes (34): SESSION_LABELS, defaults, props, busy, classicLabels, {deckId}, error, load() (+26 more)

### Community 20 - "Audio And Room Chat"
Cohesion: 0.08
Nodes (23): playAnswerSound(), playChatPop(), playPageTurn(), playRoomLockSound(), playTones(), preparePageSound(), soundsEnabled(), accepted (+15 more)

### Community 21 - "Queezo README"
Cohesion: 0.19
Nodes (11): Auth environment configuration (AUTH_ENV, AUTH_TRUSTED_ORIGINS), How login works, Backend Python dependencies (FastAPI, SQLAlchemy, argon2-cffi, websockets), Admin Console, Multiple-Choice study API, Ollama distractor generation, Vue code location map, Vue frontend migration (+3 more)

### Community 22 - "app/main.py"
Cohesion: 0.07
Nodes (12): AuthSettings, is_card_write(), PrivateResponseHeaders, reject(), send_private(), validation_error(), health(), lifespan() (+4 more)

### Community 23 - "Distractor Cache"
Cohesion: 0.14
Nodes (22): FlashcardDistractorSource, _cache_matches(), _cache_sources(), _cached_choices(), cached_choices_for_deck(), _claim(), _deck_choices(), _fingerprint() (+14 more)

### Community 24 - "Deck Editor UI"
Cohesion: 0.05
Nodes (46): escapeContent(), insertList(), MAX_IMAGE_BYTES, renderCardContent(), renderText(), safeImageUrl(), studyShortcut(), props (+38 more)

### Community 25 - "Frontend Entry And Styles"
Cohesion: 0.07
Nodes (22): setSoundsEnabled(), accountPage(), app, auth(), authentication, deck(), legacy, profile() (+14 more)

### Community 26 - "benchmark_performance.py"
Cohesion: 0.12
Nodes (18): ai_status(), configured_model(), configured_database(), main(), online_snapshot(), read_only(), restic(), restore() (+10 more)

### Community 27 - "admin_cli.py"
Cohesion: 0.17
Nodes (19): bounded_int(), build_parser(), CommandParser, identifier(), new_password(), parse_command(), read_line(), reset_password_prompt() (+11 more)

### Community 28 - "ScheduleSubjectDialog.vue"
Cohesion: 0.08
Nodes (29): {active}, addRow(), attempted, blankRow(), clockField, clockPicker, conflicts, DEFAULT_TIMES (+21 more)

### Community 29 - "Distractor Generator Tests"
Cohesion: 0.11
Nodes (26): DistractorGenerationError, generate(), generate(), reply(), run_generator(), run(), test_attempt_deadline_bounds_a_stalled_response(), test_connection_failure_preserves_previously_accepted_candidates() (+18 more)

### Community 30 - "room_study.py"
Cohesion: 0.15
Nodes (29): lifespan(), RoomQuestion, RoomSession, shuffled_options(), advance(), assign_host(), challenge_points(), claim_preparation() (+21 more)

### Community 31 - "HomeSchedule.vue"
Cohesion: 0.14
Nodes (20): {active}, day, entries, loadError, message, nextClass, now, picked (+12 more)

### Community 32 - "Profile Settings"
Cohesion: 0.08
Nodes (27): field, model, shown, {active,signal}, auth, busy, changePassword(), confirm (+19 more)

### Community 33 - "models.py"
Cohesion: 0.12
Nodes (15): require_user(), get_db(), get_db_factory(), get_write_db(), upgrade_baseline(), migrate_profile_customization(), migrate_profiles(), copy_shared() (+7 more)

### Community 34 - "ScheduleTimePicker.vue"
Cohesion: 0.08
Nodes (29): apply(), dialog, emit, fine, hand, hour, isMinute, keydown() (+21 more)

### Community 35 - "Study API Tests"
Cohesion: 0.27
Nodes (17): presentation(), review(), test_card_review_marks_activity_but_reveal_does_not_and_deletion_keeps_day(), start(), test_all_cards_are_two_sided_and_require_reveal(), test_changed_difficulty_increases_target(), test_changed_difficulty_reduces_target(), test_concurrent_duplicate_rating_counts_once() (+9 more)

### Community 36 - "Friends Drawer"
Cohesion: 0.09
Nodes (25): background, busy, data, drawer, failure, friends, incoming, inviting (+17 more)

### Community 37 - "app/schemas.py"
Cohesion: 0.13
Nodes (14): calculate_gwa(), CalculationInput, CalculationSummary, CourseInput, CourseSummary, calculate(), CardImport, CardInput (+6 more)

### Community 38 - "SharedStudyView.vue"
Cohesion: 0.10
Nodes (22): sharedMultipleChoiceRoute(), advance(), card, clock, {data:deck,error}, deadline, deckLink, done (+14 more)

### Community 39 - "ProfileView.vue"
Cohesion: 0.04
Nodes (56): buttonFeedback, choicesError, dialog, emit, limits, options, pending, problem (+48 more)

### Community 40 - "services/activity.py"
Cohesion: 0.21
Nodes (6): completed_pomodoro(), CompletedPomodoro, get_activity(), activity_view(), mark_study_day(), today_manila()

### Community 41 - "Compose.Backup Group"
Cohesion: 0.08
Nodes (23): condition, volumes, build, depends_on, env_file, environment, restart, volumes (+15 more)

### Community 42 - "Pomodoro Core Group"
Cohesion: 0.25
Nodes (18): advanceTimer(), currentTask(), DEFAULT_SETTINGS, durationMs(), nextTask(), pauseTimer(), PHASES, remainingMs() (+10 more)

### Community 43 - "create_user"
Cohesion: 0.08
Nodes (21): create_user(), migrate_card_images(), ActivityDay, login(), test_friends_consent_presence_and_profile_privacy(), test_profile_friendship_transitions_and_avatar(), activity_day(), test_completed_pomodoro_marks_current_manila_day_once() (+13 more)

### Community 44 - "distractors.py"
Cohesion: 0.13
Nodes (13): generate_distractors(), _keyboard_pattern(), _literal_length(), _parse_candidates(), _reject_json_constant(), _request_messages(), AI failure and deck-answer fallback, Shared cache lookup and generation (+5 more)

### Community 45 - "Compose.Dev Group"
Cohesion: 0.10
Nodes (20): environment, frontend, AUTH_TRUSTED_ORIGINS, CHOKIDAR_USEPOLLING, QUEEZO_PROXY_TARGET, condition, command, depends_on (+12 more)

### Community 46 - "Components Group"
Cohesion: 0.14
Nodes (20): distractors, Application REST and sockets, auth router / service / dependencies, distractor_cache, study / study_scheduler, SQLite / SQLAlchemy models, decks / community / ownership, room_study.RoomEngine (+12 more)

### Community 47 - "vue-router"
Cohesion: 0.13
Nodes (16): devDependencies, vite@8.3.8, @vitejs/plugin-vue@6.0.11, engines, node, name, private, scripts (+8 more)

### Community 48 - "Profileabout Group"
Cohesion: 0.11
Nodes (16): {active,signal}, addInterest(), bio, bioField, bioLength, editing, emit, interestField (+8 more)

### Community 49 - "test_auth.py"
Cohesion: 0.17
Nodes (22): get_settings(), AuthSession, login(), provision(), test_account_rate_limit_is_persisted_and_returns_retry_after(), test_argon2id_password_hash_and_minimum_length(), test_cross_account_data_isolation_covers_crud_study_and_dashboard(), test_email_normalization_and_case_insensitive_duplicate_rejection() (+14 more)

### Community 50 - "Test Sharing Group"
Cohesion: 0.16
Nodes (3): CardPatch, validate_card_image(), no_urls()

### Community 51 - "evaluate.py"
Cohesion: 0.09
Nodes (13): cache(), traced_generate(), MeasuredTransport, evaluate_fallback(), generate(), live_metadata(), main(), make_fixture() (+5 more)

### Community 52 - "ref_node_assert"
Cohesion: 0.14
Nodes (8): passwordStrength(), highestStreak(), shuffle(), strength, cards, assert, {chromium}, valid

### Community 53 - "ScheduleActions.vue"
Cohesion: 0.10
Nodes (25): {active, signal}, archiveDate, backToHistory(), clearDialog, closeMenu(), confirming, currentRead(), error (+17 more)

### Community 54 - "test_admin_console.py"
Cohesion: 0.18
Nodes (13): publish_success(), operator(), run(), test_concurrent_suspensions_have_one_committed_change(), suspend(), test_deck_restore_preserves_history_and_replaces_share_link(), test_dedicated_hash_attempt_limits_and_rotation(), test_interactive_commands_and_inactivity() (+5 more)

### Community 55 - "multipleChoiceSession"
Cohesion: 0.36
Nodes (9): multipleChoiceSession(), clearPoll(), poll(), readState(), report(), run(), schedule(), fixture() (+1 more)

### Community 56 - "utcnow"
Cohesion: 0.13
Nodes (32): check_origin(), optional_user(), authenticate(), change_password(), error(), login(), login_account(), login_error() (+24 more)

### Community 57 - "test_achievements.py"
Cohesion: 0.13
Nodes (23): write_transaction(), AchievementCredit, UserAchievement, Achievement, _advance(), manila_day(), record(), finish_successfully() (+15 more)

### Community 58 - "test_profiles.py"
Cohesion: 0.35
Nodes (11): add_user(), make_deck(), patch(), public_path(), test_avatar_only_update_keeps_other_settings_and_updates_account(), test_avatar_rolling_limits_and_unchanged_values(), test_concurrent_avatar_changes_share_one_remaining_slot(), test_display_name_cooldown_immutable_username_and_validation() (+3 more)

### Community 59 - "PomodoroView.vue"
Cohesion: 0.14
Nodes (18): playTimerPress(), addTask(), PHASE_NAMES, dismissTimerAlert(), act(), actionLabel, {active}, adding (+10 more)

### Community 60 - "main"
Cohesion: 0.19
Nodes (12): main(), SafeArgumentParser, test_cli_refuses_noninteractive_login_and_nonroot_recovery(), configure_prompts(), test_cli_cancelled_secure_prompt_creates_no_account(), test_cli_creates_normalized_account_with_secure_prompts_and_no_secret_output(), test_cli_has_no_plaintext_password_argument(), test_cli_invalid_or_unconfirmed_credentials_do_not_create_accounts() (+4 more)

### Community 61 - "Test Scheduler Group"
Cohesion: 0.33
Nodes (10): apply_rating(), CardState, choose_next(), test_arbitrary_rating_changes_always_finish(), test_completed_cards_excluded_and_latest_target_used(), test_deterministic_with_seed(), sequence(), test_earliest_virtual_position_does_not_fabricate_reviews() (+2 more)

### Community 62 - "admin.py"
Cohesion: 0.19
Nodes (24): moderate_profiles(), ProfileReport, audit_read(), audit_view(), backup_info(), count(), database_info(), deck_view() (+16 more)

### Community 63 - "ScheduleView.vue"
Cohesion: 0.09
Nodes (27): refresh(), changeFormat(), useNow(), adopt(), clearSchedule(), deleteSubject(), loadSchedule(), restoreSchedule() (+19 more)

### Community 64 - "services/study_rooms.py"
Cohesion: 0.17
Nodes (30): RoomInvite, RoomMember, RoomMessage, StudyRoom, active_lineup(), close(), configure(), connected() (+22 more)

### Community 65 - "Gwaview Group"
Cohesion: 0.17
Nodes (17): formatGradeDisplay(), normalizeGradeInput(), {active,signal}, addCourse(), clear(), courses, emptyCourse(), enter() (+9 more)

### Community 66 - "friends.py"
Cohesion: 0.19
Nodes (14): Friendship, SessionPresence, friend_profile(), FriendRequest, FriendResponse, identity(), list_friends(), mark_presence() (+6 more)

### Community 67 - "measure"
Cohesion: 0.10
Nodes (14): main(), measure(), sample_rss(), traced_lookup(), traced_pending(), traced_prepare_cached(), traced_save(), walk_pending() (+6 more)

### Community 68 - "Compose Group"
Cohesion: 0.20
Nodes (14): environment, AUTH_COOKIE_SECURE, AUTH_ENV, AUTH_PUBLIC_SIGNUP, AUTH_TRUSTED_ORIGINS, DATABASE_URL, FORWARDED_ALLOW_IPS, MCQ_MAX_PENDING_JOBS (+6 more)

### Community 69 - "pomodoro.js"
Cohesion: 0.17
Nodes (20): createState(), clockText(), latestAlert, liveNotifications, load(), notify(), permissionStatus(), save() (+12 more)

### Community 70 - "Components Group"
Cohesion: 0.27
Nodes (13): DecksView / DeckView / SharedView, FriendsDrawer / friends.js, GwaView, Same-origin JSON API, RoomInvitations / rooms.js, Browser storage and notifications, PomodoroView / pomodoro.js, ProfileView / ProfileSettings / PeopleView (+5 more)

### Community 71 - "Compose Group"
Cohesion: 0.17
Nodes (11): name, services, volumes, queezo_data, x-auth-environment, AUTH_COOKIE_SECURE, AUTH_ENV, AUTH_PUBLIC_SIGNUP (+3 more)

### Community 72 - "Deployment Group"
Cohesion: 0.18
Nodes (12): backend container Uvicorn :8000, backup container, queezo_backups, gwa container Uvicorn :8000, Browser / operator machine, queezo_data volume, frontend-dev container Vite HMR, frontend container Nginx :80 (+4 more)

### Community 73 - "Compose Group"
Cohesion: 0.20
Nodes (11): condition, restart, backend, gwa, depends_on, command, condition, depends_on (+3 more)

### Community 74 - "Compose Group"
Cohesion: 0.18
Nodes (11): ip_range, subnet, ipam, ipv4_address, networks, ports, restart, config (+3 more)

### Community 75 - "01 System Overview Group"
Cohesion: 0.28
Nodes (4): Queezo apps: Flashcards, GWA, Pomodoro, Queezo project instructions, Database recovery and AI reliability, Queezo AI project context

### Community 77 - "Room joining and invitation validation"
Cohesion: 0.50
Nodes (4): CSRF requirement for invite response, Lobby participant insertion, Room joining and invitation validation, Spectator insertion

### Community 78 - "Cat Group"
Cohesion: 0.18
Nodes (11): Profile avatar set, Cat avatar icon, Chicken avatar icon, Cow avatar icon, Dog avatar icon, Duck avatar icon, Fish avatar icon, Fox avatar icon (+3 more)

### Community 79 - "Profileachievements Group"
Cohesion: 0.35
Nodes (7): {name, unlocked}, {achievements, owner}, earnedCount, items, achievementProgress(), sortedAchievements(), unlockedDate()

### Community 80 - "study.py"
Cohesion: 0.29
Nodes (15): StudySession, StudySessionCard, owned_query(), exit_session(), get_session(), get_summary(), rate(), require_presentation() (+7 more)

### Community 81 - "test_password_management.py"
Cohesion: 0.29
Nodes (17): audits(), browser(), change(), console(), make_account(), sessions_of(), stored_hash(), test_admin_reset_requires_an_authenticated_operator_and_no_public_route() (+9 more)

### Community 82 - "Test Card Import Group"
Cohesion: 0.38
Nodes (8): cards_of(), import_cards(), test_card_limit_is_checked_for_the_whole_batch(), test_import_appends_in_order_without_touching_existing_cards_or_history(), test_import_never_calls_ollama(), test_imports_require_the_deck_owner_and_csrf(), test_invalid_entries_reject_the_whole_import(), test_repeated_or_concurrent_submissions_save_once()

### Community 83 - "Study Rooms Group"
Cohesion: 0.27
Nodes (10): Challenge timer and scoring, Collaborative submission and reveal, Room creation and invitation, Host handoff and termination, Join and readiness, Live invitation delivery, Notification WebSocket, RoomEngine (+2 more)

### Community 84 - "test_ownership_migration.py"
Cohesion: 0.20
Nodes (10): assign_legacy(), list_unowned(), migrate_ownership(), academic_content(), ownership_engine(), test_additive_migration_is_repeatable_and_does_not_assign_existing_records(), test_assigned_records_cannot_be_reassigned(), test_conflicting_study_owner_rejects_assignment() (+2 more)

### Community 85 - "init_database"
Cohesion: 0.11
Nodes (15): enable_wal(), init_database(), make_engine(), upgrade_achievements(), upgrade_admin_console(), upgrade_room_codes(), upgrade_shared_distractors(), anonymous_client() (+7 more)

### Community 86 - "pytest"
Cohesion: 0.28
Nodes (9): legacy_cards(), main(), repair_cards(), pre_migration_snapshot(), legacy_engine(), test_explicit_atomic_conversion_and_idempotent_database_guards(), test_incomplete_or_invalid_conversion_rolls_back(), test_new_database_rejects_non_two_sided_cards() (+1 more)

### Community 87 - "Compose Group"
Cohesion: 0.50
Nodes (8): healthcheck, healthcheck, healthcheck, interval, retries, start_period, test, timeout

### Community 88 - "Distractors Group"
Cohesion: 0.36
Nodes (8): Failed, Filling, Generating, Hit, Lookup, Persisted, Publishing, Waiting

### Community 89 - "Study Rooms Group"
Cohesion: 0.32
Nodes (8): round: Aborted, round: Advanced, round: Answering, round: Failed, round: Paused, round: Pending, round: Prepared, round: Reveal

### Community 90 - "Pomodoro Group"
Cohesion: 0.29
Nodes (8): Reset timer / Play / Skip controls, Four study sessions then long break, manual phase start, Pastel-blue rounded card theme, Phase tabs (Study / Short break / Long break), Pomodoro timer screen, Session tracker (0 of 4, dots 1-4, total), Free study task hint, 25:00 countdown display with progress bar

### Community 91 - "test_gwa.py"
Cohesion: 0.24
Nodes (9): calculate(), gwa_client(), test_decimal_units_and_half_up_display_rounding(), test_exact_classification_boundaries_before_display_rounding(), test_failed_subject_is_reported_separately_from_average(), test_invalid_course_fields(), test_invalid_course_lists(), test_one_and_fifteen_courses_and_optional_subject() (+1 more)

### Community 92 - "Compose Group"
Cohesion: 0.38
Nodes (7): build, volumes, context, dockerfile, build, build, backend

### Community 93 - "test_sharing.py"
Cohesion: 0.26
Nodes (10): make_deck(), switch_account(), test_community_limit_order_and_unassigned_exclusion(), test_ordinary_study_text_allowed(), test_owner_visibility_changes_preserve_title_and_rename_preserves_visibility(), test_public_deck_search_matches_titles_and_keeps_visibility_rules(), test_public_unlisted_readonly_and_private_revocation(), test_shared_routes_require_auth_and_copy_requires_csrf() (+2 more)

### Community 94 - "Container Architecture Group"
Cohesion: 0.33
Nodes (7): backend (FastAPI), Browser application (Vue 3), Queezo database (SQLite volume), gwa (FastAPI), frontend (Nginx), Ollama, Student

### Community 95 - "Flashcards Group"
Cohesion: 0.38
Nodes (7): Create Deck primary button, Deck card actions: Open deck and Study, Deck card grid (Science, English, Mathematics), Deck search bar with Search button, Pastel-blue theme with color-coded deck covers and decorative background, Sort decks dropdown (Newest first) with deck count, Your Decks page (flashcard deck library)

### Community 96 - "test_crud.py"
Cohesion: 0.20
Nodes (9): StudyReview, test_deck_and_card_crud(), test_deck_cascade_removes_all_study_data(), test_invalid_cards(), test_invalid_decks(), test_limit_and_concurrent_last_slot(), test_missing_resources_and_empty_study(), test_partial_card_validation() (+1 more)

### Community 97 - "Browser Components Group"
Cohesion: 0.40
Nodes (6): Same-origin JSON API, Vue application main.js/App.vue, DecksView/DeckView/SharedView, RoomView / RoomChat, session.js / AuthView.vue, StudyOptions/StudyView/MultipleChoiceView

### Community 98 - "Study Rooms Group"
Cohesion: 0.73
Nodes (6): session: Countdown, session: Open, session: Preparing, session: Results, session: Reveal, session: Waiting

### Community 99 - "System Context Group"
Cohesion: 0.33
Nodes (6): Ollama, Operator, Queezo, Restic repository, Student, Visitor

### Community 100 - "Gwa Calculator Group"
Cohesion: 0.40
Nodes (6): Add course / Clear / What's my GWA? buttons, 15-course limit, Your courses form (Subject optional, Units, Grade rows; max 15), Result panel (empty state with sigma icon), GWA Calculator screen, Units-weighted GWA calculation

### Community 101 - "Readme Group"
Cohesion: 0.40
Nodes (6): Boot skeleton loader, frontend/index.html entry page, SIL Open Font License 1.1 (Quicksand), Visual assets, queezo-cloud.svg, Quicksand.ttf (locally served)

### Community 102 - "cli.py"
Cohesion: 0.29
Nodes (4): account_view(), InsecurePasswordInput, manage_accounts(), secure_password()

### Community 104 - "Progressive Question Loading Group"
Cohesion: 0.40
Nodes (5): Open with server deadline, Poll session readiness, Read least unresolved position, Start or resume saved session, Render terminal state or result

### Community 105 - "Room Joining Group"
Cohesion: 0.40
Nodes (5): Authenticate caller and require CSRF, Check sender membership, friendship, capacity, Insert lobby participant, Reject invalid or full invite, Insert spectator

### Community 106 - "Queezo production readiness audit"
Cohesion: 0.18
Nodes (9): Queezo production readiness audit, H1 Production ingress HTTPS/proxy, H2 Auth write contention, H4 Storage/response amplification, H6 SQLite WAL corruption fix, Low findings L1-L2 (self-reported activity, privacy ops), Medium findings M1-M7 (share reactivation, logs, abuse, deps, observability, CI, CSP), Phase 1 operating limits (quotas, body sizes) (+1 more)

### Community 108 - "admin_auth.py"
Cohesion: 0.31
Nodes (7): AdminAudit, AdminCredential, authenticate(), current_credential(), Principal, record(), operator()

### Community 109 - "Multiplayer Study Rooms"
Cohesion: 0.22
Nodes (5): Schema version 4 (admin_credential, admin_audit), Same-deck fallback distractors, Schema v3, Multiplayer Study Rooms, Achievements (Deck Master, Studious, Hoster)

### Community 110 - "Compose Overlays Group"
Cohesion: 0.50
Nodes (4): backup container scheduled backup, queezo_backups volume, queezo_data, Optional Restic repository

### Community 111 - "Study Rooms Group"
Cohesion: 0.50
Nodes (4): invite: Accepted, invite: Declined, invite: Pending, invite: Unavailable

### Community 112 - "Study Rooms Group"
Cohesion: 1.00
Nodes (4): room: Active, room: Closed, room: Lobby, room: Results

### Community 128 - "schedule.js"
Cohesion: 0.12
Nodes (30): applyClockTime(), checks, openClock(), clock, CODE_LIMIT, COLORS, conflictSide(), convertDraft() (+22 more)

### Community 129 - "SegmentedSwitch.vue"
Cohesion: 0.47
Nodes (5): buttons, choose(), emit, keydown(), props

### Community 149 - "Shared distractor verification"
Cohesion: 0.25
Nodes (8): Backup sidecar (compose.backup.yaml), Restic encrypted off-host backups, Versioned migration with pre-migration snapshot, H3 Backup and migration rollback, Card-level distractor cache shared across solo and rooms, Shared distractor verification, Generation lease and writer fencing, Schema v3 flashcard_distractor_jobs

### Community 150 - "Base"
Cohesion: 0.33
Nodes (6): Base, FlashcardDistractorCache, FlashcardDistractorJob, ai_read(), clear_cached_distractors(), test_version_two_migration_preserves_choices_and_backfills_source()

### Community 151 - "H5 Ollama serial slot / admission queue"
Cohesion: 0.29
Nodes (6): MCQ AI admission limits, H5 Ollama serial slot / admission queue, Shared Ollama model slot, ROOM-01..05 confirmed issues, Multiplayer Study Rooms QA, ROOM-R01..R04 remaining limits

### Community 152 - "Moderation commands (suspend, unpublish, changepassword, close room)"
Cohesion: 0.25
Nodes (6): Profile interest tag list, Moderation commands (suspend, unpublish, changepassword, close room), Profile reports, Profile visibility (Public/Unlisted/Private), Deck visibility (Private/Public/Unlisted), Share tokens (32-byte URL-safe)

## Ambiguous Edges - Review These
- `PRAGMA user_version 6 migrations` → `Verification claims schema version 3 (chapter 03 says 6)`  [AMBIGUOUS]
  docs/architecture/VERIFICATION.md · relation: conceptually_related_to
- `flashcards` → `multiple_choice_questions`  [AMBIGUOUS]
  docs/architecture/diagrams/database-er.md · relation: references

## Knowledge Gaps
- **133 isolated node(s):** `Snapshot of four shuffled choices with stable IDs`, `Progressive question loading`, `15-course limit`, `Units-weighted GWA calculation`, `Boot skeleton loader` (+128 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 974 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **37 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ROOM-01..05 confirmed issues` connect `H5 Ollama serial slot / admission queue` to `Room View UI`, `room_study.py`, `Study Room API`?**
  _High betweenness centrality (0.149) - this node is a cross-community bridge._
- **Are the 113 inferred relationships involving `User` (e.g. with `optional_user()` and `require_user()`) actually correct?**
  _`User` has 113 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Snapshot of four shuffled choices with stable IDs`, `Progressive question loading`, `15-course limit` to the rest of the system?**
  _133 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `DashboardView.vue` be split into smaller, more focused modules?**
  _Cohesion score 0.08374384236453201 - nodes in this community are weakly interconnected._
- **Why does `Multiple-Choice preparation activity` connect `utcnow` to `Multiple-Choice UI`, `distractors.py`?**
  _High betweenness centrality (0.113) - this node is a cross-community bridge._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `PRAGMA user_version 6 migrations` and `Verification claims schema version 3 (chapter 03 says 6)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `flashcards` and `multiple_choice_questions`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._