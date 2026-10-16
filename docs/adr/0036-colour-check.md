# 0036: Colour check for Dolby Vision profile 5 damage

- Status: accepted
- Date: 2026-10-16

## Context
The owner found episodes playing green and purple. Neagley S01E02 (4K web) had
been re-encoded by FileFlows with NVENC on 7 October. The source was Dolby
Vision profile 5, whose picture is IPTPQc2, not YCbCr. The encoder treated it
as ordinary video and dropped the Dolby Vision record and all colour tags, so
the wrong colours are now in the picture itself, on every player. The only
remedy is another copy.

Almost the whole library (about 22,000 of 22,850 files) went through FileFlows.
A scan of ReelHaven's database found 1,310 files that are 10-bit and have no
HDR or Dolby Vision information. 58 of them came from 4K releases (the whole
Neagley season, 22 web movies, 28 Blu-ray movies). Metadata alone can't separate
damaged files from harmless 10-bit SDR encodes.

Measured on the owner's files, the average chroma of frames spread through a
file separates them. Damaged E02 sits clearly below neutral on both U and V
(about 0.47 of full scale: green). An intact Dolby Vision 5 file read raw looks
the same, but it keeps its record, so players decode it. Normal HDR10 and SDR
files sit near 0.5, or warm (U low, V high).

## Decision
- **Candidates** (from the stored probe, no file access): the main video is
  10-bit or more, its HDR type is SDR, it has no Dolby Vision record, and its
  colour primaries and transfer are missing or unspecified (or weren't recorded
  by older scans).
- **Measurement:** ffmpeg decodes one frame at each of six points (5 % to 95 %
  of the duration), scaled down, and records the average Y, U and V
  (signalstats), normalised to 0–1. It runs at low priority, one file at a time,
  in the background, and again when the file changes. Results are stored on the
  file (`media_files.colour_check`) with the file's size and time.
- **Verdict "wrong colours":** the mean U and mean V are both below 0.485, and
  at least four of the six frames have both below 0.495. That is a green cast
  throughout, not one green scene. Otherwise "ok".
- **Action:** wrong-colours files are listed on the Review page as **Wrong
  colours** and aren't re-encoded or track-changed. They get the library's
  wrong-language action like damaged files (ADR-0035): with Quarantine or
  Delete, the file is moved aside and Sonarr/Radarr are asked to blocklist the
  release and search for another.
- **Washed-out HDR (lost HDR10 tags)** is not detected or repaired yet. Adding
  PQ tags to a file that is really SDR would ruin it, so that waits for a real
  sample to validate against. The measurements stored for every candidate will
  help.

## Consequences
- Around 1,300 candidates in the owner's library: a few hours of background
  checking at low priority after updating. New and changed files are checked as
  they're scanned.
- A green-heavy film could in principle match. Requiring the cast across most of
  the film, and only on untagged 10-bit SDR files, keeps that unlikely, and with
  Flag the owner decides.
