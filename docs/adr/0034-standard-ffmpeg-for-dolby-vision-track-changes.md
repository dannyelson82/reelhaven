# 0034: A standard ffmpeg for track changes on Dolby Vision files

- Status: accepted
- Date: 2026-10-15

## Context
The owner's failure report (ADR-0033) showed every track-only change on a Dolby
Vision file failing the HDR check: profile 8.1 files came out as HDR10, and
profile 5 files came out looking like SDR, which would play with wrong colours.
Tested on two of the owner's files, the jellyfin-ffmpeg 8.1.3 build (ADR-0003)
drops the Dolby Vision configuration record on any stream copy, to Matroska and
to MP4. It logs the record on the output stream but never writes it. Upstream
FFmpeg 8.1.3 keeps it with the same command. The bug has been reported to
jellyfin-ffmpeg.

Re-encoding Dolby Vision files was already skipped (it would lose the layer), so
track changes are the only path that touches them.

## Decision
- The image also ships a **standard static FFmpeg build**: BtbN FFmpeg-Builds,
  `n8.1.3` GPL linux64, from the month-end release `autobuild-2026-09-30-13-08`
  (month-end builds are kept long-term), verified by SHA-256 at build time and
  installed as `/opt/ffmpeg-copy/ffmpeg` together with its licence.
- `REELHAVEN_COPY_FFMPEG` points at it. **Track-change (remux) jobs on Dolby
  Vision sources** run with it. Everything else, including all GPU work, stays on
  jellyfin-ffmpeg.
- The HDR check after every job is unchanged. If the copy ffmpeg is missing (as
  in development) or ever loses Dolby Vision, the job fails safely as before,
  with an error that says so. The file isn't retried automatically, and the
  original is kept (the owner's option 2 as a fallback).
- When jellyfin-ffmpeg is fixed, this can be removed again. The upstream issue is
  followed during development.

## Consequences
- The image grows by about 170 MB.
- Two ffmpeg builds to keep up to date. The pinned build is bumped by hand.
- Profile 5 and 8 files get their audio and subtitle changes with Dolby Vision
  intact.
