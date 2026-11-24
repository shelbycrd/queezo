# Multiplayer Study Rooms

Open **Friends**, expand a friend, and choose **Invite to Study** to start a private room. The first invitation is created in the same operation as the room. Invitations update live in **Notifications**, which also has links to rejoin your rooms. The room code is a reference for participants. Joining requires an invitation sent by a current member who is your friend.

## Play and replay

- The host selects a deck from the lobby cards and chooses a mode. Public decks are eligible. Selecting an owned private or unlisted deck grants invited members access inside this room. Deck, mode, and timer changes save automatically and sync to all players. The grant ends when the owner leaves, and a previously public deck stops being usable if its owner makes it private without a room grant.
- At least two connected players, including the host, must be present. Each other connected player marks themselves ready in the main lobby. Spectators, disconnected members, and pending invitees do not affect readiness. A change to the deck or mode resets readiness.
- **Collaborative** locks a choice when clicked and reveals answers after active players finish, then shows the group’s avatars above their answer buttons for five seconds. The host can pause during review.
- **Challenge** defaults to 30 seconds per question. Clicking an answer locks it immediately. The server starts the countdown only when it opens a question and closes each round on the deadline or after everyone answers. It awards up to 1,000 points for a correct answer and updates rankings in Participants during review.
- Late arrivals can watch and use chat. The host can return everyone to the lobby after results, which clears readiness and gives spectators a place in the next session.

## Recovery and limits

A refresh rejoins the same membership and resumes the current round. The server tracks connections and gives participants 45 seconds to reconnect before skipping missing answers or transferring leadership. If no active player remains after the grace period, the session ends with the results already recorded. When the host leaves, the longest-standing remaining member becomes host automatically. The room closes if the host is the last member. Rooms also close after 30 minutes without activity or a connected participant. Completed results stay in SQLite when participants leave or when the room returns to the lobby. The current interface shows the current session’s results.

Chat accepts up to 500 characters per message and five messages in ten seconds per account. Answer lock-in and grades have short sounds that follow the existing study sound setting. Chat asks each account to acknowledge a safety notice once per browser and offers an incoming-message sound that users can mute. The room view includes the latest 80 messages, and each room retains up to 500 across sessions. A room holds at most six people, including spectators. Each participant can invite from a paginated list of their own friends, with existing invitations and room membership shown on each row.

## Deployment and verification

Rebuild the backend, GWA, and frontend gateway together. Startup upgrades supported older databases to schema version 3 with a verified pre-migration snapshot. The gateway forwards WebSocket upgrades to FastAPI. Configure trusted HTTPS origins as usual in production.

Room messages and submitted answers use authenticated, CSRF-protected HTTP requests. The server sends participant-specific snapshots over an authenticated WebSocket, checks membership and session validity throughout the connection, and retains the authoritative clock and score in SQLite. Preparation follows the persisted shuffled order and uses the existing Ollama and distractor cache services. A shared five-second countdown begins once the first questions are ready. The rest can prepare in the background. Players wait together if the next question is pending. Failed questions are skipped in their original positions.

Run the room regression suite with `python -m pytest tests/test_study_rooms.py` from `backend`. Run the frontend suite with `npm test` from `frontend`.

The optional two-browser check lives in `frontend/tests/e2e/study-rooms.cjs`. Point `QUEEZO_ROOM_TEST_URL` at an isolated Compose project with a disposable SQLite volume and signup enabled. The check creates synthetic accounts and decks, so use a test deployment. With Playwright installed, run `node tests/e2e/study-rooms.cjs` from `frontend`. Set `QUEEZO_PLAYWRIGHT` to load a separately installed Playwright package or `QUEEZO_ROOM_BROWSER_EXECUTABLE` to use an existing Chromium or Edge installation.

For the audit results, fixes, and remaining beta risks, see [Study Rooms QA](quality/STUDY_ROOMS_QA.md).
