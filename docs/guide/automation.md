---
title: Automatic processing
order: 85
summary: Let libraries keep themselves tidy, with a nightly rescan and a pause button.
---

# Automatic processing

Each library has a **Watch mode**, set at the top of the library page:

| Watch mode | What happens |
|---|---|
| **Off** (default) | Nothing happens unless you start it: scans, dry runs and **Apply** are all manual. |
| **Watch** | New and changed files are found and planned (see the **Dry run** tab). Nothing is changed. |
| **Automatic** | Everything in the library that needs work is processed, **the backlog included**, and new files are handled as they're found. |

Switching to **Automatic** asks you to confirm. Look at the [Dry run](dry-run.md)
first: that's exactly the work it will do.

## Safety rails

- **Re-encoding waits for a [test run](test-run.md)**: an Automatic library
  only re-encodes after a test run with its current profile is approved.
  Track-only changes (removing tracks, fixing defaults, converting audio)
  start straight away.
- **Files that need review are never touched** (wrong language, no wanted
  audio, unreadable).
- **A few files at a time**: ReelHaven keeps about four jobs per library in
  the queue and adds more as they finish, so the [Jobs](jobs.md) page stays
  readable and new files get their turn.
- **No automatic retries**: a file whose job failed or that you cancelled is
  left alone until the file changes. Use **Try again** to retry it yourself.
- Every original still goes to the [recycle bin](recycle-bin.md) for 14 days.

## How new files are found

For libraries set to **Watch** or **Automatic**:

- **Folder watcher**: when files are added, renamed or removed, the library is
  rescanned about a minute later (a whole season arriving counts as one
  change). Files still being copied are left for a follow-up scan a few
  minutes later.
- **Every 15 minutes** each watched library is rescanned anyway. Unraid
  shares don't report every change (for example files written straight to a
  disk share like `/mnt/disk1`), and this catches them.
- **Nightly rescan**: a full rescan once a day (below).

Rescans are quick: only new or changed files are read.

## Nightly rescan

Libraries set to **Watch** or **Automatic** are rescanned once a day to find
new and changed files. Change the time, or switch it off, under **Rescan
watched libraries every night** at the bottom of the **Libraries** page. The
time is the server's local time (the container's `TZ` setting).

## Pause everything

**Pause all processing** on the **Jobs** page stops new jobs from starting,
manual or automatic. Jobs that are already running finish. While paused, an
orange banner on the Jobs page and the Dashboard says so; **Resume** carries on
where it left off.

## Coming in later updates

Sonarr/Radarr webhooks (new imports noticed the moment they finish) and
telling Plex, Sonarr and Radarr about changed files.
