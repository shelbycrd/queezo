# Database recovery and AI reliability

## SQLite runtime

The backend, GWA and backup images load SQLite **3.54.1** in Python. The image obtains the official amalgamation in a build stage and checks its SHA3-256 digest before compiling. The runtime build fails if Python loads a different version. The isolated runtime reported source ID `2026-10-16 14:45:20 555e07ef33f69a0957d24d8e555b702464a131d6f1607f4c3c1e4551e8e6ca76`. The upstream [3.51.3 release](https://sqlite.org/releaselog/3_51_3.html) fixed the WAL-reset race. See the [3.54.1 release](https://sqlite.org/releaselog/3_54_1.html) and [download checksum](https://sqlite.org/download.html).

The previous Python image loaded Debian `libsqlite3-0:amd64 3.46.1-7+deb13u2`. [Debian's backport diff](https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=1141424) describes FTS5 fixes and does not establish a WAL-reset backport. That system package can still appear in `dpkg-query`; the application uses the pinned shared library under `/opt/queezo/sqlite`. Check `sqlite3.sqlite_version` and `SELECT sqlite_source_id()` in the actual Python process, as the image build does. Keep WAL, the 30-second busy timeout, and foreign keys enabled. Keep the live DB and its WAL on the same local persistent filesystem.

## Configure backups

The optional Compose file runs a backup process separately from app requests. It mounts the existing database volume read-only and writes to a separate `queezo_backups` volume.

```powershell
docker compose -f compose.yaml -f compose.backup.yaml up -d --build --wait
```

The first successful run occurs after startup and runs daily at 00:00 UTC thereafter. Temporary failures retry within one hour and do not stop the app. Check `docker compose -f compose.yaml -f compose.backup.yaml logs backup` for a verified snapshot; a successful Compose startup alone does not confirm a backup. Each snapshot uses SQLite's online backup API, validates integrity and foreign keys, and publishes a self-contained file. Local files are readable by the backup owner and must be protected as student records. Default retention is 14 days. Set `BACKUP_RETENTION_DAYS` to 1–365 in `.env.backup`. Keep sufficient storage for the source database, an in-progress copy and the retained backups.

Create `.env.backup` from `.env.backup.example` to configure restic. Set `RESTIC_REPOSITORY` and the repository password plus credentials for your chosen backend. You can use `RESTIC_PASSWORD_FILE` with an operator-mounted secret instead of putting the password in the environment file. Restic encrypts snapshot contents before uploading. Restrict storage and credential access, and keep an offline recovery copy of the repository key. Initialize a dedicated repository once, from the deployment environment:

```powershell
docker compose -f compose.yaml -f compose.backup.yaml run --rm --no-deps --entrypoint restic backup init
```

Schedule and manual commands upload verified snapshots when a repository is configured. Restic retains snapshots within the configured number of days and always keeps the latest in the Queezo tag/host group. Retention also prunes unused repository data, so the credential needs the relevant permissions. Restrict permissions to this repository. Without a configured repository, only local backups exist. Monitor the sidecar logs and time since last successful upload, and alert when no current backup is available. A local backup on the same host is not off-host disaster recovery. For repository options and credential handling, see the [restic documentation](https://restic.readthedocs.io/en/v0.18.0/030_preparing_a_new_repo.html).

Run or verify a manual snapshot while the application is healthy:

```powershell
docker compose -f compose.yaml -f compose.backup.yaml run --rm --no-deps backup backup
docker compose -f compose.yaml -f compose.backup.yaml run --rm --no-deps backup verify /backups/SNAPSHOT.db
```

Replace `SNAPSHOT.db` with the name printed by the backup command. If an upload fails, the local validated snapshot remains available. Check repository reachability and credentials without placing secret values in logs.

## Restore into a separate file

Recover from the encrypted repository to a staging directory first, or use a verified local snapshot directly.

```powershell
docker compose -f compose.yaml -f compose.backup.yaml run --rm --no-deps --entrypoint restic backup snapshots --tag queezo-sqlite
docker compose -f compose.yaml -f compose.backup.yaml run --rm --no-deps --entrypoint restic backup restore SNAPSHOT_ID --target /backups/staged
docker compose -f compose.yaml -f compose.backup.yaml run --rm --no-deps backup restore /backups/staged/backups/SNAPSHOT.db --output /backups/recovered.db
```

Replace both placeholders with the selected repository snapshot ID and file name. For a local backup, use `/backups/SNAPSHOT.db` as the source. The restore command verifies both source and output, refuses an existing output or the configured live path, and removes login sessions from the recovery copy. It does not modify the live database, source backup, counts, or user passwords.

Before an operator promotes the recovery copy, boot it using a separate project and fresh volume. Verify account logins, profile and deck ownership, deck privacy, cards, study history and foreign keys. Observe recovery time and record the latest commit present in the copy. For a real cutover, explicitly stop **all** processes on the affected volume, including the backup process. Save an independent copy of the original volume, including any SQLite sidecars. Have the operator install the tested copy with the correct ownership and keep the original DB and sidecars together and separate for rollback. Start the matching app release and recheck health before reopening access. Never replace an active SQLite file or combine a recovered database with old WAL/SHM files.

## Migration and rollback

Startup takes SQLite's writer lock before inspecting `PRAGMA user_version`. An empty file is initialized directly. A pre-versioned database first receives a verified snapshot in `/data/.migration-backups/<database-name>/`; only then do the existing additive migrations run. Schema changes and the new version commit together. Current versions skip migration; unknown versions fail closed. The three most recent local pre-migration copies are kept per database. The legacy card repair and operator ownership assignment also snapshot before editing data. Treat migration snapshots as sensitive. Keep an independent verified online backup before deploying an upgrade because the automatic preflight copy lives on the database volume.

To run startup migrations explicitly for the configured database during an upgrade window:

```powershell
docker compose run --rm --no-deps backend python -m app.sqlite_ops migrate
```

If a migration fails, review the startup error stage. Recheck disk space, permissions, source integrity, and legacy card preconditions. For rollback, verify the appropriate pre-migration file using the same restore-to-fresh-file procedure, then rehearse it with the previous app version. Do not decrement the version on the live database.

## AI capacity and failure handling

| Backend variable | Default | Valid range |
|---|---:|---:|
| `MCQ_MAX_PENDING_JOBS` | 16 | 1–64 |
| `MCQ_MAX_PENDING_PER_USER` | 3 | 1–16, capped by global limit |
| `MCQ_PREPARATION_TIMEOUT_SECONDS` | 900 | 1–1800 |
| `OLLAMA_REQUEST_TIMEOUT_SECONDS` | 60 per attempt | 0.1–300 |

The worker counts admission reservations and active jobs, including work waiting for Ollama or cancellation to settle. Per-user and shared limits return HTTP 429 with a retry hint; a closing worker returns HTTP 503. SQLite also keeps the existing per-user 15-minute budget. Admission time counts against the session's preparation deadline. Duplicate jobs for the same attempt are ignored. One Ollama call runs at a time. Cache reads and cached decks can progress while that slot is occupied. Existing adaptive retries, same-deck fallback, stable options, and progressive order still apply. A restart settles unfinished work as interrupted, and the existing retry or continue actions remain available as applicable. Classic remains independent of Ollama.

Watch backend preparation logs for admission pressure and aggregate failure outcomes. These logs do not include card text or model responses. Use a single backend worker and private Ollama endpoint. Before inviting real users, validate queue limits and cancellation on the intended hardware. An abandoned HTTP call can stop local work while Ollama on the host is still completing a request.
