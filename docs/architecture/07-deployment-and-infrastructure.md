# 07 · Deployment and infrastructure

[Architecture index](README.md) · [Deployment diagrams](diagrams/deployment.md) · [Recovery runbook](../production/DATABASE_RELIABILITY.md)

## Base Compose deployment

| Service | Runtime | Exposure and persistence |
| --- | --- | --- |
| `frontend` | Nginx serving assets built with Vue and Vite | Host loopback `127.0.0.1:${APP_PORT:-8080}` maps to port 80. Depends on healthy backend and GWA. |
| `backend` | FastAPI/Uvicorn | Bridge-only port 8000. Owns migrations, authentication, application API, workers and health. Mounts `queezo_data:/data` read-write. |
| `gwa` | Separate FastAPI/Uvicorn entrypoint using the same image | Bridge-only port 8000. Shares the SQLite volume for session validation and waits for a healthy backend. |
| Ollama | Host dependency or configured external endpoint | Default `http://host.docker.internal:11434`. The base Compose file defines no Ollama service or published port. |

Compose uses one bridge with configurable address space and a reserved Nginx IP. Uvicorn trusts forwarding only from that IP by default. Nginx rewrites forwarded client-IP headers from its own peer address. It serves the SPA fallback, proxies `/api/gwa/` and `/gwa/` to GWA, sends other `/api/` traffic to the backend, and upgrades room URLs that end in `/live`. It sends no-store headers on ordinary API requests, applies edge throttling and body limits, and omits paths and query strings from its access format. Startup checks are HTTP health probes. They do not establish live model availability or external TLS. [Compose](../../compose.yaml), [Nginx routes](../../nginx/nginx.conf), [security headers](../../nginx/security-headers.conf), [backend image](../../backend/Dockerfile)

## Development and optional backup overlays

Use `docker compose -f compose.yaml -f compose.dev.yaml up -d --build --wait` for the Docker development workflow. The overlay runs Node 24/Vite on loopback port 5173, mounts the frontend source for HMR, stores dependencies in a named volume, and forwards API HTTP and WebSocket requests to Nginx. Both APIs trust the local dev origins in this overlay. The [development guide](../DEVELOPMENT.md) covers the local Node workflow. [Development overlay](../../compose.dev.yaml), [proxy configuration](../../frontend/vite.config.js)

The backup overlay mounts the data volume read-only and a separate volume for backup output. It writes a verified online SQLite snapshot after startup and thereafter daily at 00:00 UTC. Failures retry separately from application traffic. The default retention is 14 days, adjustable with `BACKUP_RETENTION_DAYS`. If a Restic repository is configured, the sidecar copies snapshots there. [Backup configuration template](../../.env.backup.example) Restore to a separate file, verify integrity and foreign keys, and follow the runbook for a controlled cutover. Restored copies revoke prior browser sessions. The local backups volume alone shares the host failure domain. [Backup overlay](../../compose.backup.yaml), [backup and restore code](../../backend/app/sqlite_ops.py), [runbook](../production/DATABASE_RELIABILITY.md)

## Configuration and production boundary

| Area | Controls |
| --- | --- |
| SQLite | `DATABASE_URL`. Both services use `sqlite:////data/queezo.db` in base Compose. |
| Authentication | `AUTH_ENV`, `AUTH_COOKIE_SECURE`, exact `AUTH_TRUSTED_ORIGINS`, and `AUTH_PUBLIC_SIGNUP`. Production startup requires secure cookies and HTTPS trusted origins. |
| Proxy | `APP_PORT`, `QUEEZO_PROXY_IP`, `QUEEZO_PROXY_SUBNET`, `QUEEZO_PROXY_DYNAMIC_RANGE`. Keep the forwarded-header trust list consistent with the actual proxy hop. |
| Inference | `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_REQUEST_TIMEOUT_SECONDS`, `MCQ_PREPARATION_TIMEOUT_SECONDS`, `MCQ_MAX_PENDING_JOBS`, `MCQ_MAX_PENDING_PER_USER`. Validate with the deployed model and expected workload. |

Base Compose serves HTTP on loopback. External HTTPS termination, domain, gateway addresses, firewall policies, CDN behavior, and alert routing require deployment configuration and were outside source verification. No cloud topology is named here. Nginx access logs record status, bytes, and timing. Uvicorn access logs are disabled in container commands. Backend workers log sanitized events, and backup freshness can be checked through the backup CLI. These are health and diagnostic mechanisms. A site-wide metrics or alerting platform is not configured here. [Environment template](../../.env.example), [authentication configuration](../../backend/app/auth/config.py), [health and lifespan](../../backend/app/main.py), [operational audit](../production/READINESS_AUDIT.md)
