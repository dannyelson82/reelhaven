# 0019: Encoding defaults

- Status: accepted
- Date: 2026-10-06

## Context
Phase 0.4 adds video encoding. The owner's server has NVIDIA and Intel GPUs;
playback happens through Plex/Jellyfin on a range of devices.

## Decision
- Default codec **HEVC**, **10-bit** output (Main10). AV1 is available per profile
  on GPUs whose test encode succeeds; H.264 for very old clients.
- Default quality **Balanced**. Built-in profiles: *High quality*, *Balanced*,
  *Small*; user profiles can be added.
- Encoder preference when several devices can do the job: NVIDIA → Intel →
  AMD → CPU. CPU encoding is off unless enabled.
- Quality is stored as one normalised level (1 = smallest, 10 = best) and mapped
  per encoder family (NVENC `-cq`, QSV `-global_quality`, VAAPI `-qp`, x265/SVT
  `-crf`) in one tested module.

## Consequences
- Wide playback compatibility with large savings.
- Clients that can't decode HEVC 10-bit (rare, mostly pre-2017) need a profile
  with 8-bit or H.264.
