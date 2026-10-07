# Quality calibration (0.4)

Measured on 2026-10-07 with `backend/scripts/calibrate_quality.py`. The
resulting tables are in `backend/src/reelhaven/quality.py`.

## Goal

A profile's quality level (1-10) should give the same visual quality whichever
device encodes the file. The CPU encoders are the reference; each GPU family
gets the value whose average XPSNR matches the CPU at that level.

## Method

- Six 10-second 1080p clips from Creative Commons films, converted to lossless
  H.264 first so every decode is identical (cutting a clip without re-encoding
  leaves damaged first frames that decode differently each time and wreck the
  comparison): *Tears of Steel* (people indoors, a street, a VFX-heavy shot),
  *Sintel* (a detailed room, a dark scene), *Big Buck Bunny* (animated
  meadow). The clips are kept outside the repo.
- Every detected device encoded every clip over its whole value range (steps
  of 2) with ReelHaven's real video arguments at the *Balanced* speed: HEVC
  10-bit and H.264 8-bit.
- Quality: luma XPSNR against the clip, averaged over the clips. Each GPU
  value is interpolated to the level's CPU XPSNR and rounded to a whole value.
  Where two levels rounded to the same value, the lower level got the next
  value up so each level stays distinct.
- Hardware: Intel i5-8400 (x265/x264), NVIDIA RTX 3060 (NVENC), Intel UHD 630
  (Quick Sync), jellyfin-ffmpeg 8.1.3.

## Results (HEVC 10-bit)

| Level | x265 CRF | XPSNR | kbps | NVENC CQ | kbps | QSV GQ | kbps |
|---|---|---|---|---|---|---|---|
| 1 | 31 | 33.9 | 662 | 36 | 795 | 28 | 1127 |
| 4 *Small* | 26 | 36.8 | 1317 | 31 | 1555 | 23 | 2142 |
| 6 *Balanced* | 24 | 37.8 | 1762 | 29 | 2040 | 21 | 2727 |
| 8 *High quality* | 20 | 39.8 | 3196 | 25 | 3626 | 17 | ~4600 |
| 10 | 18 | 40.8 | 4329 | 23 | 4849 | 15 | 6202 |

At the same quality, NVENC files are about **15 % larger** than x265 and
Quick Sync (UHD 630) files about **55 % larger**; for H.264, about 5 % and
40 %. The GPUs are many times faster (1080p: NVENC ~9x, QSV ~4x x265
*medium*).

Before calibration, NVENC used CPU value + 1. That encoded at much higher
quality than intended: *Balanced* files were about 1.8x the intended size.
Quick Sync used the CPU value, which encoded at lower quality than intended.

## Per-clip spread (x265, Balanced)

XPSNR at CRF 24 ranged from 36.0 dB (*Tears of Steel*, people) to 39.6 dB
(*Big Buck Bunny*). With the test run's rating thresholds (Indistinguishable
≥ 40, Very good ≥ 36, Good ≥ 33), *Balanced* rates *Very good* and *High
quality* rates *Very good* to *Indistinguishable*. The thresholds are kept.

## Not calibrated yet

AV1 on NVENC/QSV (no AV1-capable GPU available; they borrow the HEVC table)
and AMD VAAPI (no AMD GPU; uses the CPU table). Rerun the script on such
hardware and update `quality.py`:

```
cd backend
uv run python scripts/calibrate_quality.py CLIPS_DIR results.json
```
