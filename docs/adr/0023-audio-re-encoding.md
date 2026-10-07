# 0023: Audio re-encoding in profiles

- Status: accepted
- Date: 2026-10-07

## Context
Profiles could only copy audio, or compress lossless tracks to E-AC-3 during a
video re-encode. Many files carry 3-6 Mbit/s lossless or high-bitrate audio,
and mimicking a sample with compact audio needs a way to reproduce it.
ARCHITECTURE.md §7.1 already allows transcoding to E-AC-3, AAC or Opus.

## Decision
- A profile's audio is **copy**, or **convert to E-AC-3, AAC or Opus** at a
  per-channel bitrate (channel-aware, e.g. 6 channels at 96 kbit/s each =
  576 kbit/s). The existing "compress lossless to E-AC-3" option stays as a
  preset of the same mechanism.
- Which tracks are converted: **lossless tracks always; lossy tracks only when
  their bitrate is at least 1.5x the target**. Object audio (TrueHD Atmos,
  E-AC-3 JOC, DTS:X) is **always copied**. Channels are never added
  (no upmix); AAC is limited to 5.1, Opus to 7.1, E-AC-3 to 5.1, and tracks
  with more channels are copied.
- **Audio-only jobs**: when only the audio would change (the video is already
  efficient or the library has no video encoding), the file is processed with
  the video **copied untouched**. The same verification, minimum saving
  (default 10 % of the whole file) and recycle bin apply.
- Track language, title, default/forced flags and order are kept.

## Consequences
- Big savings on files with lossless audio even when the video is fine.
- Lossy-to-lossy conversion only happens when it clearly saves space, which
  limits generational loss.
- The verifier must accept a changed audio codec on the converted tracks;
  the planner must estimate audio savings.
