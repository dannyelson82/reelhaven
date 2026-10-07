# Phase 0.6: Automation

Planned with the owner on 2026-10-07. Decisions: ADR-0025.
Release: **v0.6.0**.

Goal: libraries keep themselves tidy. New files are noticed (webhooks, folder
watcher, nightly rescan), libraries set to *Automatic* are processed on their
own (backlog included) behind the existing safety rails, and Plex and
Sonarr/Radarr are told when files change.

Owner decisions: all three triggers; Automatic includes the backlog; no
processing window; notify Plex and Sonarr/Radarr (Jellyfin later).

| # | Chunk | Contents |
|---|-------|----------|
| 1 | Design records | ADR-0025, this plan |
| 2 | Watch modes + auto-processor | Watch mode per library (Off / Watch / Automatic), scheduled rescan (nightly, configurable), auto-processor that tops up the queue under the safety rails, global Pause / Resume, "left to do" per library; guide |
| 3 | Folder watcher | `watchdog` inotify + polling fallback, 2-minute stability, rescans only what changed; guide |
| 4 | Webhooks | `POST /api/v1/webhook/{sonarr,radarr}` (API key, strict payloads, path mappings), setup steps in the UI and guide |
| 5 | Notifiers | Plex integration (address + token, partial folder scan), Sonarr/Radarr rescans, 60 s batching, notification log; guide |
| 6 | Wrap-up | Docs, release v0.6.0 |
