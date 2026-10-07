---
title: Mimic a file
order: 65
summary: Pick a file you like and get a profile that reproduces its quality across a library.
---

# Mimic a file

Found a file whose size and picture you like? **Mimic** reads how it was made
and builds a [compression profile](profiles.md) that gives your other files
the same kind of result.

## Steps

1. Go to **Profiles** and click **Mimic a file**.
2. Choose the **Library** the file is in and **Search** for it by name. (The
   sample must be in one of your libraries; to use a file from another
   computer, copy it into a library folder first.)
3. Click the file. ReelHaven reads it (this takes a few seconds; the file
   isn't changed) and shows what it found and the **Suggested profile**.
4. Click **Use these settings**. The profile editor opens, named
   *Like <file name>*, with a note about each value:
   - **read from the sample**: the file recorded it, e.g. the exact quality
     setting (CRF) an x264/x265 encode used.
   - **estimated**: worked out from the file's bitrate. Content matters a lot
     (grainy film needs more bits than animation), so treat it as a starting
     point.
   - **default**: nothing to go on; ReelHaven's normal choice.
5. Adjust anything you like and click **Save**. The profile list shows
   *Mimicked from …* under it.

Then choose the profile for a library and check it with a
[test run](test-run.md) before re-encoding the whole library.

## What is copied from the sample

| Setting | From the sample |
|---|---|
| **Video codec** | HEVC, AV1 or H.264, as the sample. Other codecs (e.g. MPEG-2) become HEVC. |
| **10-bit output** | On when the sample is 10-bit (not for H.264). |
| **Quality** | Read from x264/x265 settings when present; otherwise estimated from bits per pixel. A sample made by a GPU encoder (NVENC, Quick Sync) is recognised and accounted for: they need more bits for the same quality. |
| **Audio** | If the sample's main track is compact E-AC-3, AC-3, AAC or Opus, the profile converts big tracks to that codec at the same bitrate per channel (AC-3 becomes E-AC-3). Lossless, Atmos/DTS:X or unknown audio means **Copy every track unchanged**. |
| **Maximum resolution** | Never set: your files keep their resolution. |
| **Speed** | Not recorded by encoders; **Balanced**. |
