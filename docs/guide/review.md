---
title: Review
order: 95
summary: One page for every file that needs your decision, from wrong-language releases to failed jobs.
---

# Review

**Review** (in the menu) lists every file that needs a decision, from all
libraries. The number next to it counts what's left to look at. Nothing on
this page changes files by itself.

## Tabs

| Tab | What it means |
|---|---|
| **Wrong language** | None of the audio is in the library's languages, for example an English film with only Spanish audio: probably the wrong release. It shows the audio languages and the title's original language. Untagged audio never counts as wrong. |
| **Wrong colours** | The picture plays green and purple on every player. Usually a Dolby Vision file (profile 5, common in 4K streaming releases) that another program re-encoded without understanding Dolby Vision. ReelHaven doesn't process these files; they need another copy. See [Colour check](#colour-check). |
| **Failed** | The file's last job failed. The original wasn't changed. **Try again** queues it again. |
| **Can't be read** | ReelHaven couldn't read the file. It may be damaged, or still being copied; it's read again when it changes. If it's still unreadable a day after it last changed, it counts as damaged and gets the library's action for files that need another copy (see below). |
| **Waiting** | The title's original language hasn't been looked up yet, so the file waits (see [Languages](languages.md)). Not counted in the menu: it sorts itself out. |

Files ReelHaven kept unchanged on purpose aren't listed here, because there's nothing to
decide. They're under **Stats → Kept as is**: **No gain** (re-encoding or converting
the audio didn't make the file smaller) and **Not re-encoded** (Dolby Vision and HDR10+
files). See [Stats](stats.md#kept-as-is).

## Actions

- **Quarantine** and **Delete** (wrong-language files, after you confirm) move
  the file out of the library and ask Sonarr/Radarr for another release (see
  [Languages](languages.md#wrong-language-files)).
- **Open library** goes to the file's library.
- **Ignore** hides the file from that tab and from the count. If the file
  changes (a new release, for example), it shows up again.
  **Show ignored** lists ignored files, with **Show again**.

The page updates every minute.

## Review report

With [Developer options](developer.md) on, **Download review report** (top of
the page) saves one text file with every file listed here: why it's here, its
tracks, its original language and where ReelHaven found it, and the last
job's error for failed files. It also lists what was resolved in the last 90
days, because ReelHaven keeps a record of everything the page has shown.
Passwords and API keys are removed; file and folder names stay in.

## Files that need another copy

Wrong-language files, wrong-colour files and damaged files (unreadable for more
than a day) all need a fresh download. Each library's **Files with none of
your languages** setting (see [Languages](languages.md)) decides what happens
to them:

- **Flag for review** (default): they're listed here and nothing changes.
- **Quarantine** or **Delete**: ReelHaven moves the file out of the library and
  asks Sonarr or Radarr to blocklist that release and search for another. In
  an Automatic library the new download is then processed like any new file.
  Quarantined files are kept for the recycle bin's days to keep.

**Quarantine** and **Delete** buttons on this page do the same for one file.

## Colour check

ReelHaven looks for files whose picture has the wrong colours: 10-bit video
with no colour or HDR information and no Dolby Vision record. That's what a
Dolby Vision profile 5 file looks like after another program re-encoded it as
ordinary video. For each such file it looks at 12 frames spread through it, and
if most of the picture is green throughout, the file goes on the **Wrong
colours** tab.

The check runs in the background at low priority, one file at a time, and pauses
when processing is paused. After updating, the first pass over a large library
can take a few hours. New and changed files are checked as they arrive.
