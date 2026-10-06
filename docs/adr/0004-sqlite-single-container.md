# 0004: SQLite and an in-process job queue in a single container

- Status: accepted
- Date: 2026-10-06

## Context
Unraid users install apps from one template. A separate database or Redis
container makes installation harder and is a common source of support issues.

## Decision
One container. SQLite in WAL mode (SQLAlchemy + Alembic) for all state,
including a persisted job queue processed by in-process worker pools (one per
encode device, plus a CPU pool for remux jobs).

## Consequences
- One-template install, backups are a copy of `/config`.
- Jobs survive restarts.
- Not suitable for multi-node processing; that is a non-goal for v1.
- All writes go through a single writer pattern to avoid lock contention.
