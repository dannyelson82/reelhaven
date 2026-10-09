# 0030: Rescan only the folders that changed

- Status: accepted
- Date: 2026-10-09

## Context
ADR-0025's folder watcher started a **full** library scan for every burst of
changes, again after the "still being copied" time, for every Sonarr/Radarr
webhook, and as a safety net every 15 minutes. A full scan walks every folder
and checks every file, then runs the language lookup. On the owner's TV library
(30,000+ episodes on an Unraid array) that meant the library was being rescanned
almost constantly.

## Decision
- **Changes rescan their title folder only**: the top-level folder under the
  library root the change happened in (a film's folder, a series' folder).
  A partial scan walks just those folders, reads new or changed files there,
  removes files that disappeared from them, and recognises moves between them
  (a renamed folder reports both names). Changes that can't be placed in a
  folder (the library root itself, a video file directly in the root) still
  rescan the whole library.
- **Webhooks** name the series or film path: they rescan that folder.
- **The 15-minute safety net** no longer reads files: it compares the
  modification times of the library's folders with the previous check
  (a file added, removed or renamed changes its folder's time) and partially
  rescans the title folders that changed. The first check after start only
  records the times.
- The **nightly rescan** and **Scan library** stay full scans; they catch what
  the cheap checks can't (a file rewritten in place, a video file added
  directly to the library root).
- Bursts still settle for 30 seconds and get a follow-up after the stability
  time, now for the same folders.

## Consequences
- A new episode costs a scan of one series folder instead of the library.
- The safety net costs one directory listing per folder instead of a stat of
  every file.
