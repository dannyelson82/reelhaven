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
- **Files wait for the language lookup**: a new file is only processed once its
  title's original language has been looked up (see [Languages](languages.md)).
- **Every GPU kept busy**: ReelHaven queues enough jobs per library to fill
  every enabled graphics card (each card's **At the same time** on the
  [Hardware](hardware.md) page, added up) plus two waiting, and queues the
  next one the moment a job finishes. It never queues the whole library at
  once, so the [Jobs](jobs.md) page stays readable and new files get their
  turn.
- **No automatic retries**: a file whose job failed or that you cancelled is
  left alone until the file changes. Use **Try again** to retry it yourself.
- Every original still goes to the [recycle bin](recycle-bin.md) (14 days
  unless you changed it).

## How new files are found

For libraries set to **Watch** or **Automatic**:

- **Folder watcher**: when files are added, renamed or removed, only the
  film's or series' folder they're in is rescanned, about a minute later (a
  whole season arriving counts as one change). Files still being copied are
  left for a follow-up check of the same folder a few minutes later.
- **Sonarr/Radarr webhooks**: imports, upgrades, renames and deletes are
  noticed the moment they happen, and only that series or film is rescanned
  (set up on the [Integrations](integrations.md) page).
- **Every 15 minutes** ReelHaven also compares the folders' last-changed times
  with the previous check, without opening any files, and rescans the folders
  that changed. Unraid shares don't report every change (for example files
  written straight to a disk share like `/mnt/disk1`), and this catches them.
- **Nightly rescan**: a full rescan once a day (below). It also catches what the
  quicker checks can't, such as a file replaced in place or a video placed
  directly in the library's top folder.

While a folder-only rescan runs, the library page names the folders being
checked. Only new or changed files are ever read again.

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

## Plex, Sonarr and Radarr

After files are replaced, Plex, Sonarr and Radarr are told to look again
(about a minute later, in batches). See [Integrations](integrations.md).
