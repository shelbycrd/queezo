# Multiplayer Study Rooms

Open **Friends**, expand a friend, and choose **Invite to Study** to start a private room. Invitations and links to rejoin your rooms are in **Notifications**. The room code is a reference for participants. Joining requires an invitation sent by a current member who is your friend.

## Play and replay

- The host selects a deck and mode. Public decks are eligible. Owners can explicitly share their own private or unlisted deck with invited members for this room. The grant ends when the owner leaves, and a previously public deck stops being usable if its owner makes it private without a room grant.
- At least two connected participants must be present. The host can start after the other connected participants are ready. A change to the deck or mode resets readiness.
- **Collaborative** reveals answers after active players finish, then shows the group’s results for five seconds. The host can pause during review.
- **Challenge** defaults to 30 seconds per question. Players choose their answer and select **Lock In**. The server closes each round on the deadline or after everyone answers. It awards up to 1,000 points for a correct answer and updates rankings during review.
- Late arrivals can watch and use chat. The host can return everyone to the lobby after results, which clears readiness and gives spectators a place in the next session.

## Recovery and limits

A refresh rejoins the same membership and resumes the current round. The server tracks connections and gives participants 45 seconds to reconnect before skipping missing answers or transferring leadership. Rooms close after 30 minutes without activity or a connected participant. Completed results stay in SQLite when participants leave or when the room returns to the lobby. The current interface shows the current session’s results.

Chat accepts up to 500 characters per message and five messages in ten seconds per account. The room view includes the latest 80 messages, and each room retains up to 500 across sessions. A room holds at most six people, including spectators.

## Deployment and verification

Rebuild the backend, GWA, and frontend gateway together. Startup automatically upgrades schema version 1 to 2, taking a verified pre-migration snapshot before creating the room tables. The gateway forwards WebSocket upgrades to FastAPI. Configure trusted HTTPS origins as usual in production.

Room messages and submitted answers use authenticated, CSRF-protected HTTP requests. The server sends participant-specific snapshots over an authenticated WebSocket, checks membership and session validity throughout the connection, and retains the authoritative clock and score in SQLite. Preparation uses the existing Ollama and distractor cache services and skips failed questions in their original positions.

Run the room regression suite with `python -m pytest tests/test_study_rooms.py` from `backend`. Run the frontend suite with `npm test` from `frontend`.

The optional two-browser check lives in `frontend/tests/e2e/study-rooms.cjs`. Point `QUEEZO_ROOM_TEST_URL` at an isolated Compose project with a disposable SQLite volume and signup enabled. The check creates two synthetic accounts and a deck, so use a test deployment. With Playwright installed, run `node tests/e2e/study-rooms.cjs` from `frontend`. Set `QUEEZO_PLAYWRIGHT` to load a separately installed Playwright package or `QUEEZO_ROOM_BROWSER_EXECUTABLE` to use an existing Chromium or Edge installation.
