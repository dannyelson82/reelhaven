---
title: Compression profiles
order: 60
summary: Choose how video is re-encoded, per library.
---

# Compression profiles

A **profile** decides how video is re-encoded. Each library uses one profile,
or none.

## Choose a profile for a library

At the top of a library page, pick the profile from the drop-down:

- **No encoding (languages only)**: the video is never re-encoded. Only the
  [language](languages.md) changes are made.
- **Encode: *profile name***: files that would benefit are re-encoded.

Changing a library's profile, or editing the profile it uses, means a new
[test run](test-run.md) is needed before the whole library can be re-encoded.

## Built-in profiles

| Profile | Quality | Speed | Good for |
|---|---|---|---|
| **High quality** | 8 / 10 | Slow | Films you care about most; smaller savings. |
| **Balanced** | 6 / 10 | Balanced | The default: good quality, large savings. |
| **Small** | 4 / 10 | Balanced | Shows you watch once; biggest savings. |

All three use HEVC 10-bit, keep the source resolution and copy audio
unchanged. Built-in profiles can't be edited, but **Copy** makes an editable
copy.

## Profile settings

| Setting | What it does |
|---|---|
| **Video codec** | **HEVC (H.265)** plays almost everywhere (default). **AV1** is smaller but needs newer GPUs and players. **H.264** only for very old devices. |
| **Quality** | 1 (**Smallest**) to 10 (**Best**). Higher means bigger files closer to the original. |
| **Speed** | **Fast**, **Balanced** or **Slow (smaller files)**. Slower settings squeeze a little more out of each file. |
| **10-bit output** | Better quality per byte and no colour banding. Not available for H.264. |
| **Maximum resolution** | Larger videos are scaled down; smaller ones are never scaled up. |
| **Audio** | **Copy every track unchanged**, or **Compress lossless tracks (TrueHD, DTS-HD MA, FLAC, PCM) to E-AC-3**. |
| **Add a stereo AAC track for older devices** | Adds one extra stereo track. |

Always true, whatever the profile:

- Atmos and DTS:X audio is copied unchanged.
- **Dolby Vision** and **HDR10+** files aren't re-encoded (it would break
  them). HDR10 and HLG are kept as HDR.
- A file is only re-encoded when the estimated saving is at least 10 %, and
  the real result is checked again after encoding (see [Jobs](jobs.md)).

Which encoder does the work (NVIDIA, Intel, AMD or CPU) is set on the
[Hardware](hardware.md) page. ReelHaven translates the quality level into each
encoder's own setting.
