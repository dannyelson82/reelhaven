# 0010: Audit log ships in phase 0.1

- Status: accepted
- Date: 2026-10-06

## Context
The roadmap placed the audit log in phase 0.7, but SECURITY.md needs it
earlier: login lockouts (phase 0.1) and destructive actions (phase 0.3) must
be recorded.

## Decision
The `audit_log` table and a small `audit.record(actor, action, target, detail)`
helper are part of phase 0.1. Phase 0.7 keeps the audit log **UI**.

## Consequences
- Security events are captured from the first release.
- The 0.7 work is only the viewing page.
