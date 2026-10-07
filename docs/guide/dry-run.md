---
title: Dry run and applying changes
order: 50
summary: See exactly what ReelHaven would do with a library, then apply it.
---

# Dry run and applying changes

A **dry run** works out what ReelHaven would do with every file in a library,
using its [language policy](languages.md) and
[compression profile](profiles.md). **Nothing is changed.**

## Run a dry run

Open a library, go to the **Dry run** tab and click **Run dry run**. You'll
see:

- **Files**: how many files the library has.
- **Would change**: how many would be re-encoded, and how many get track
  changes only.
- **Space saved**: the estimated saving.
- **Need review**: files flagged *Wrong language* or *No wanted audio*, plus
  files that couldn't be read. These are never touched.

Switch between **Changes**, **Needs review** and **All** to see each file's
plan. **Run again** refreshes it after you change a setting.

## What the plans mean

- **Re-encode**: the video is compressed with the library's profile (track
  changes happen in the same pass).
- **Remux**: only the tracks change: unwanted ones are removed, default flags
  are fixed, and audio is converted if the profile says so (see
  [Profiles](profiles.md)). The video is copied untouched.
- **Nothing**: the file already matches your settings.

A file isn't re-encoded when it wouldn't help, for example when:

- the estimated saving is below the profile's minimum (10 %),
- it's already in the profile's codec at a low bitrate,
- it was already encoded by ReelHaven with this profile,
- an earlier encode with this profile didn't save enough,
- it's **Dolby Vision** or **HDR10+** (re-encoding would break or lose
  metadata), or it's HDR and the profile is H.264.

The reason is shown in the file's details.

## Apply

Click **Apply to N files**, read the summary and confirm. The files are
queued on the [Jobs](jobs.md) page.

- Each new file is checked before it replaces the original.
- Originals go to the [recycle bin](recycle-bin.md) for 14 days.
- If the library changed since you looked, nothing is queued and you're asked
  to look again.

## Before the test run is approved

Re-encoding a whole library needs an approved **[test run](test-run.md)**
with the current profile first. Until then the button reads **Apply track
changes to N files**: it applies the files that only need track changes, and
the files waiting to be re-encoded get their track changes when they're
re-encoded later.

Single files can always be applied from their details (**Apply to this
file**), including re-encodes.
