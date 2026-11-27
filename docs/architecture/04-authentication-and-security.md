# 04 · Authentication and security

[Architecture index](README.md) · [Registration and login sequence](diagrams/sequences/accounts-and-cards.md#registration-and-login)

## Account and session lifecycle

Web registration validates the exact signup fields, normalizes the email and username and enforces matching 11–1024-character passwords. Usernames are immutable via the profile API and the baseline SQLite trigger. Passwords use Argon2id with time cost 3, memory cost 65,536 KiB, and parallelism 4. Email is syntactically validated. `email_verified` is currently returned as false. Production public signup defaults to disabled, with operator CLI provisioning available.

Login reserves IP/email attempt counters before performing expensive verification. It compares against a dummy Argon2 digest for nonexistent accounts, then rechecks the account identity and hash under a short write transaction before rotating the caller's session. Signup hashes before its final insert. Password changes (Settings → Security → Change Password, `POST /api/auth/password`) require an authenticated, CSRF-protected request. They verify the current password with Argon2 outside the write transaction, require a matching 11–1024-character new password that differs from the current one, and reserve one of five attempts per account per 15 minutes before verifying, so concurrent guesses cannot bypass the limit. A successful change stores the new Argon2 hash only if the stored hash is unchanged (otherwise 409), deletes every session including the caller's, and clears the cookie. The browser then returns to login and tells other tabs to sign out. Administrators can reset a password only through the server-local admin console (`users changepassword`), never through an HTTP route. Logout invalidates the current session. The backend performs these operations with a four-slot admission semaphore in the main process.

The browser receives a random bearer token in a seven-day, host-only, HttpOnly, SameSite=Lax cookie with `Path=/`. Secure mode uses a `__Host-` cookie name and expects HTTPS. SQLite stores only the token's SHA-256 digest. `/api/auth/me` restores account details and derives CSRF from the cookie token using HMAC-SHA256 with a domain separator. The Vue API wrapper holds CSRF in memory and sends it on mutations. Authenticated unsafe methods check Origin when supplied, reject cross-site Fetch Metadata, and compare the CSRF value in constant time. Signup/login check origin before credentials are handled.

Sources: [credential and token functions](../../backend/app/auth/service.py), [authentication routes](../../backend/app/auth/router.py), [dependency checks](../../backend/app/auth/dependencies.py), [cookie policy](../../backend/app/auth/config.py), [Vue API client](../../frontend/js/api.js).

## Access boundaries

| Resource | Enforced boundary |
| --- | --- |
| Owned deck, flashcard, and Classic history | User owns the parent resource. Legacy records with null owners stay out of ordinary account queries. |
| Shared decks and solo practice | A signed-in requester needs the share token and current public/unlisted visibility. Private decks remain owner-scoped. A shared MC session remains requester-scoped and is revalidated against the current share token digest and status. |
| Profile and friendships | Public profiles can be discovered. Public and unlisted profiles can be read by visitors with the link. Private profiles require the owner. Accepted friendships add presence visibility where the profile route permits it. Owner email, password hash, and session credentials stay out of public profile payloads. |
| Class schedule | Subjects, meetings and the time-format preference belong to one account. Every read and write filters by the signed-in owner and uses CSRF-protected HTTP. Another account's subject or meeting id yields 404 or 422 with no hint that it exists, and nothing in a schedule is visible on profiles or to other users. |
| Global search | Requires a signed-in user. Public-deck results need `visibility='public'`, a live owner, no `unpublished_at` and a share token, and exclude the caller's own decks; My Decks matches only `owner_id == caller`. Users are public, non-suspended profiles, and results never include email. Queries are trimmed to 80 characters and matched with escaped `LIKE`, pages are capped at 30 rows and 1000 pages. Recent-visit references are regex-validated and re-checked per request, so another account's private or unlisted-unauthorized refs resolve to nothing. |
| Achievements | Owners see progress, goals, and unlock times. Visitors see names and descriptions of earned achievements only, on profiles they may already read. Progress, unlock dates, and the study or hosting activity behind them are never sent to visitors. |
| Active room | Current membership is required. Invite acceptance rechecks the sender's membership, accepted friendship, and available capacity. Only the host can change settings, start, pause Collaborative review, or return from results. |
| Room-private deck | The selected deck must still belong to the recorded deck owner and that owner must remain a member for the grant to apply. A room grant permits snapshots inside that room, including for spectators. It does not give members owner-level deck access. |
| Socket snapshots | A trusted explicit Origin and valid session cookie are required; room sockets also require current membership. Both sockets recheck session expiry. Mutations are HTTP+CSRF. Before reveal the player sees the option text and their own selection, without the correct option ID, answer photo or other selections. |
| Operational tools | Profile report review, targeted cache refresh, and account operations are executed through the CLI. There is no browser administrator role. |

Sources: [deck access](../../backend/app/services/ownership.py), [sharing and token rotation](../../backend/app/routers/decks.py), [shared solo revalidation](../../backend/app/services/multiple_choice.py), [profiles](../../backend/app/routers/profiles.py), [rooms and sockets](../../backend/app/routers/study_rooms.py), [room snapshot](../../backend/app/services/room_study.py), [CLI](../../backend/app/cli.py).

## Abuse controls and sensitive data

- Authentication uses a 15-minute window with limits of 10 signup attempts per IP, 30 login attempts per IP, five per normalized email, and five password-change attempts per account. Throttle keys hash email/IP identifiers where used.
- The HTTP middleware caps the query string at 8 KiB, auth bodies at 16 KiB, and typical API bodies at 64 KiB. Card writes have a media-derived allowance. Nginx separately applies 5 MiB body size and a per-client request rate of 60 requests/s with burst 120 to proxied API locations.
- Study and deck routes bound deck count, card count, per-image and aggregate photo storage, session/history size, and preparation queue admission. Room services bound room counts, member capacity, invite actions, socket concurrency, and chat size and rate. See [data flows](08-data-flows-and-lifecycle.md) and [Study Rooms](06-multiplayer-study-rooms.md) for operational bounds.
- Card text is validated for URL-like input and rendered as escaped text/list markup. Inline PNG, JPEG, and WebP photos are validated and bounded. Room chat uses Vue text interpolation with length and character checks. Validation is specific to these entry points rather than a general-purpose content moderation system.
- Nginx access logs contain status, byte count, and duration. Backend access logging is disabled in the image. In production, the middleware checks HTTP hosts against configured origins and blocks the bundled API documentation routes. SQLAlchemy hides SQL parameter values, and public validation errors omit submitted inputs. API responses use no-store; Nginx adds anti-framing and content-type headers.

Sources: [limits](../../backend/app/services/limits.py), [body and host controls](../../backend/app/auth/middleware.py), [image validation](../../backend/app/services/card_images.py), [URL checks](../../backend/app/services/content_policy.py), [client rendering](../../frontend/js/card-content.js), [room chat UI](../../frontend/src/components/RoomChat.vue), [proxy](../../nginx/nginx.conf), [headers](../../nginx/security-headers.conf).

## Constraints

Share tokens are bearer links for signed-in readers and rotate according to visibility changes. The service does not verify email or enforce MFA. The current CSP is a frame-ancestors policy, while content handling depends on escaping and validation. Client-reported Pomodoro completion records a study day and cannot attest to elapsed study time. The configured Compose gateway is loopback HTTP, so public HTTPS and forwarded client-IP behavior require a verified external deployment configuration. Local Ollama receives the card's Front and Back on cold generation; apply the same data-handling standards to its host and backups.

See [deployment trust boundaries](07-deployment-and-infrastructure.md) and [risks and decisions](09-architecture-decisions.md).
