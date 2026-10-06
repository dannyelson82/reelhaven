# Phase 0.1: Foundation

Status: **complete** (v0.1.0, 2026-10-06). Chunks landed as PRs #1–#8.

Planned with the owner on 2026-10-06. Decisions: ADRs 0009–0014.

Goal: an installable, secure, empty shell of ReelHaven. You log in, and the
setup wizard creates the admin account. Built by CI, published to GHCR,
installable from the Unraid template.

Each chunk is one branch and pull request; CI must pass before it is merged.

| # | Chunk | Contents |
|---|-------|----------|
| 1 | Backend skeleton | `backend/` uv project, FastAPI app factory, `/healthz`, ruff/mypy/pytest, CI backend job, design ADRs 0009–0014 |
| 2 | Frontend skeleton | `frontend/` Vite + React + TS + Mantine, oxlint/Prettier/Vitest, CI frontend job, built files served by FastAPI |
| 3 | Config and logging | Settings (env + `/config`), JSON logs to stdout + rotating file, secret-redaction filter, request-log middleware (ADR-0011) |
| 4 | Database | SQLite WAL, SQLAlchemy 2, Alembic; tables `users`, `sessions`, `settings`, `audit_log` (ADR-0010); single-writer lock |
| 5 | Authentication | Argon2id, sessions + log out everywhere, login throttling, CSRF double-submit, security headers, API key (ADR-0011), local-address bypass + trusted proxies + gateway guard (ADR-0012), setup gating (ADR-0013) |
| 6 | Setup wizard step 1 + login UI | Create-admin page, login page, app shell with logout, security settings (API key, bypass, trusted proxies) |
| 7 | Docker image | Multi-stage Dockerfile on Debian 13, jellyfin-ffmpeg, Intel/AMD drivers, PUID/PGID/UMASK entrypoint, healthcheck, image workflow (edge on main, versions on tags), vulnerability scan |
| 8 | Wrap-up | Required status checks on `main`, CodeQL, GHCR package public, Dependabot uv + npm, CLAUDE.md commands, tag `v0.1.0` |

Owner involvement: install the `edge` image on Unraid after chunk 7.

## Implementation notes
- The database layer is synchronous SQLAlchemy. FastAPI runs sync endpoints in a
  threadpool, and SQLite gains nothing from async drivers. Writes go through
  one process-wide lock (ADR-0004 single writer).
- In development, the config directory is `REELHAVEN_CONFIG_DIR` (default
  `./.dev-config`, gitignored). In the container it is `/config`.
- GitHub Actions are pinned to commit SHAs; Dependabot keeps them updated.
