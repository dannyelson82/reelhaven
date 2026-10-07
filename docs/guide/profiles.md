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
| **Audio** | **Copy every track unchanged**; **Convert lossless tracks** (TrueHD, DTS-HD MA, FLAC, PCM); or **Convert large tracks** (lossless ones, and lossy ones well above the target). See *Audio conversion* below. |
| **Add a stereo AAC track for older devices** | Adds one extra stereo track. |

## Audio conversion

When a profile converts audio, choose **Convert to** and the **Bitrate per
channel**; the editor shows what that means for stereo and 5.1.

| Codec | Default per channel | Stereo / 5.1 | Plays on |
|---|---|---|---|
| **E-AC-3** | 112 kbit/s | 224 / 640 | Almost every TV, soundbar and player |
| **AAC** | 64 kbit/s | 128 / 384 | Everything |
| **Opus** | 48 kbit/s | 96 / 288 | Smallest for the quality; some TVs can't play it |

Which tracks are converted:

- Lossless tracks always.
- With **Convert large tracks**, lossy tracks too, but only when they're at
  least 1.5 times the target bitrate. For example, with AAC at 384 kbit/s for
  5.1, a 1.5 Mbit/s DTS track is converted but a 448 kbit/s AC-3 track is
  kept, because re-encoding it would save little and cost some quality.
- **Atmos and DTS:X are always copied**, and tracks are never upmixed. Tracks
  with more channels than the codec is used for (more than 5.1 for E-AC-3 and
  AAC, 7.1 for Opus) are copied.
- Language, title, default and forced flags, and track order stay the same.

Audio is converted in the same pass when a file is re-encoded. When the video
is already efficient, ReelHaven can still convert just the audio: the video is
copied untouched. It does this when the file gets track changes anyway, or when
the audio alone saves at least the profile's minimum (10 % of the file). These
audio-only jobs don't need a [test run](test-run.md).

Always true, whatever the profile:

- Atmos and DTS:X audio is copied unchanged.
- **Dolby Vision** and **HDR10+** files aren't re-encoded (it would break
  them). HDR10 and HLG are kept as HDR.
- A file is only re-encoded when the estimated saving is at least 10 %, and
  the real result is checked again after encoding (see [Jobs](jobs.md)).

Which encoder does the work (NVIDIA, Intel, AMD or CPU) is set on the
[Hardware](hardware.md) page. The NVIDIA and Intel settings were measured so that a quality level
looks the same as on the CPU (AMD isn't measured yet).
