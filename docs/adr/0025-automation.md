# 0025: Automatic processing

- Status: accepted (when and where to rescan amended by ADR-0030)
- Date: 2026-10-07

## Context
Phase 0.6 makes ReelHaven work on its own (ARCHITECTURE.md §6.9, §6.10). The
owner chose all three triggers, automatic processing of the whole library
(backlog included), no processing window, and notifications to Plex and
Sonarr/Radarr.

## Decision
- **Watch mode per library**: *Off* (default; manual only), *Watch* (new and
  changed files are scanned and planned, nothing is changed), *Automatic*
  (everything that needs work is processed, backlog included).
- **Triggers**: Sonarr/Radarr webhooks (`POST /api/v1/webhook/{sonarr|radarr}`,
  API key), a folder watcher (inotify via `watchdog`, plus polling because
  Unraid user shares can miss events; a file waits until its size and mtime
  are stable for 2 minutes), and a scheduled rescan of every library
  (default nightly at 03:00).
- **Safety rails for Automatic**:
  - re-encodes only after an approved test run with the library's current
    profile (ADR-0020); track-only changes don't need one;
  - files flagged for review (wrong language, unreadable) are never processed
    automatically;
  - the queue is **topped up** a few files at a time per library instead of
    creating every job at once, so a **global Pause** takes effect
    immediately and new arrivals still get their turn;
  - a file that failed is not retried automatically until it changes.
- **No processing window** for now (owner decision); §6.5 keeps it as a later
  option.
- **Notifiers** after a successful replace, batched per 60 s: **Plex**
  (partial scan of the folder; new integration with address and token) and
  **Sonarr/Radarr** (rescan the series/movie). Each uses the integration's
  path mappings. Jellyfin later.

## Consequences
- Libraries can be left to tidy themselves; the dry run and test run remain
  the way to check before switching a library to Automatic.
- Topping up the queue means "In progress" counts show what's queued now, not
  the whole backlog; the library page shows what's left.
