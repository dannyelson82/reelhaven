---
title: Libraries and files
order: 20
summary: Add your media folders, scan them and look inside every file.
---

# Libraries and files

A **library** is a folder of videos under `/media`, for example
`/media/Movies` or `/media/TV`. Add one library per kind of media.

## Add a library

1. Go to **Libraries** and click **Add library**.
2. Enter a **Name**, choose the **Type** (*Movies*, *TV shows* or *Other
   videos*) and pick the **Folder**.
3. Click **Add library**. Adding a library doesn't change any files.

**Edit** lets you rename a library or change its type. **Remove library**
makes ReelHaven forget it; your files stay exactly where they are.

## Scan a library

Open a library and click **Scan library**. ReelHaven:

1. looks for video files,
2. reads each new or changed file (codec, resolution, HDR, audio and subtitle
   tracks),
3. looks up the original language of each title (see
   [Languages](languages.md)).

When it finishes, a summary shows how many files were found, read, moved or
gone, and any that couldn't be read. Files that are still being copied are
picked up by the next scan. **Refresh languages** repeats only the language
lookup, which is useful after adding an integration.

ReelHaven keeps its own working files in a hidden `.reelhaven` folder at the
root of each library. Scans ignore it.

## The Files tab

Every file is listed with its original language, video format (codec,
resolution, HDR type), audio and subtitle languages, and size. Use the search
box to find files by name, or tick **Only files that couldn't be read**.

A yellow language badge means the track has no language tag.

## File details

Click a file to open its details:

- **Original language** of the title, and where it came from (Sonarr, Radarr,
  TMDB or *set by you*). Use **Change for every file of this title** to set it
  by hand; **Go back to automatic** undoes that.
- **What ReelHaven would do** with this file: *Re-encode*, *Remux* (track
  changes only) or *Nothing*, with the reasons and the estimated saving.
  **Apply to this file** queues just this file. Single files don't need a
  [test run](test-run.md).
- Every stream in the file, with its codec, language, title and flags such as
  *default*, *forced*, *SDH* or *commentary*.
