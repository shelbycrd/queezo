# Queezo profiles

Open **Profile** from the account menu. **Edit Profile** contains the display name, bio, interests, avatar, visibility, and featured deck. **Share Profile** provides a clean `/u/<username>` link. The account UID and email remain in the signed-in **Settings → Account Settings** section.

## Visibility

| Setting | Direct profile link | Find profiles |
| --- | --- | --- |
| Public | Viewable by anyone with the link | Included |
| Unlisted | Viewable by anyone with the link | Excluded |
| Private | Owner only | Excluded |

New and existing accounts default to **Unlisted**. Their profile starts with the Cat avatar and empty bio and interest tags. A profile’s visibility does not change deck sharing. Guests who open a deck from a profile sign in before continuing through the existing shared-deck workflow.

Public profiles include the display name, username, month and year joined in the UI, avatar, bio, interests, and public-deck metadata. The featured deck must belong to the profile owner and be public. If it is deleted, made unlisted or private, or loses its share link, it is removed from the featured slot. Search applies to the separate public-deck list, which shows 12 decks per page.

## Limits and moderation

Usernames are immutable in the API and in SQLite. Display-name changes use a 14-day cooldown. Avatar changes use a rolling window of 10 per 60 minutes. Re-saving an unchanged name or avatar does not use either limit. The server serializes writes before checking cooldowns or recording reports.

Signed-in visitors can send at most five profile reports in a rolling 24-hour window, with at most one per target. Reports are available only through the operator CLI, which requires access to the backend container. Review records a timestamp and does not change the reported account.

```powershell
docker compose exec backend python -m app.cli list-profile-reports
docker compose exec backend python -m app.cli list-profile-reports --include-reviewed
docker compose exec backend python -m app.cli review-profile-report --report-id 1
```

## Database and implementation

Startup adds six profile columns to `users` and creates `profile_avatar_changes` and `profile_reports`. SQLite enforces immutable usernames and clears inaccessible featured decks. Nullable profile references and additive defaults preserve account IDs, credentials, existing decks, and study history. Existing deck URLs and the legacy friend-profile API remain available, subject to profile privacy.

| Area | Files |
| --- | --- |
| Profile API | New `backend/app/routers/profiles.py`. Updated `auth/dependencies.py`, `main.py`, and `routers/friends.py` under `backend/app/`. |
| Persistence and moderation | Updated `backend/app/models.py`, `database.py`, `profile_migration.py`, and `cli.py`. |
| Profile and discovery UI | New `ProfileView.vue`, `PeopleView.vue`, `ProfileEditor.vue`, `ReportProfileDialog.vue`, profile service, stylesheet, and three avatar SVGs. Replaced the separate `FriendProfileView.vue` with the shared profile view. |
| Routing and settings | Updated the Vue entry point, app shell, friend links, deck tile links, account service, and settings view. Nginx uses the existing SPA fallback for direct profile links. |
| Verification | Added `backend/tests/test_profiles.py` and `frontend/tests/profiles.test.mjs`, and extended the legacy account migration test in `backend/tests/test_signup.py`. |
