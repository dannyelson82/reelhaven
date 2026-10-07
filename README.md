<p align="center"><img src="assets/icon.png" width="128" alt="ReelHaven icon"></p>

# ReelHaven

**Smaller files. The right language.**

ReelHaven automatically compresses your video library on Unraid using every
GPU you have, keeps only the audio and subtitle languages you want, and keeps
Plex, Jellyfin, Sonarr and Radarr in sync.

> ⚠️ Early development (v0.6). It re-encodes and changes files only when you
> ask it to, checks every result, and keeps every original in a recycle bin
> first. Try it on a copy or a small library before trusting it with media
> you can't afford to lose.

## What works today (v0.6)
- **Libraries**: scan your folders and see every file's video, audio and
  subtitle tracks
- **Languages**: original language of each title from Sonarr, Radarr or TMDB
  (or set by hand), a language policy per library, and removal of unwanted
  audio and subtitle tracks
- **GPU encoding**: NVIDIA NVENC, Intel Quick Sync and AMD, detected with a
  real test encode; compression profiles (HEVC, AV1, H.264), calibrated so a
  quality level looks the same on NVIDIA, Intel and the CPU; files that wouldn't benefit
  (or would be harmed, like Dolby Vision) are skipped
- **Mimic**: pick a file you like and get a profile that reproduces its quality
  (read from x264/x265 settings, or estimated from the bitrate)
- **Audio conversion**: shrink lossless or oversized audio to E-AC-3, AAC or
  Opus, even when the video is already efficient (the video is then copied)
- **Dry run** showing exactly what would change, and a quality-checked
  **test run** (sizes, XPSNR/SSIM, side-by-side stills) that you approve
  before a whole library is re-encoded
- **Apply** per file or per library; every result is verified before it
  replaces the original, and originals stay in a 14-day recycle bin with
  one-click restore
- **Live progress** for every job (fps, speed, time left)
- **Automatic processing**: set a library to Watch or Automatic; new files are
  noticed by a folder watcher, Sonarr/Radarr webhooks and a nightly rescan,
  and Automatic libraries work through everything (re-encodes only after an
  approved test run). One button pauses it all
- **Keeps your apps in sync**: Plex scans the changed folders and
  Sonarr/Radarr rescan the affected series and movies

## First start
Open the web UI (port 7171) and create the admin account **before** exposing
ReelHaven to the internet: until then, whoever opens it first becomes admin.

## Planned features
- Finds files that arrived in the wrong language and can quarantine and
  re-download them
- Stats: files processed, space saved, per-GPU performance

## Documentation
- [User guide](docs/guide/)
- [Architecture](ARCHITECTURE.md)
- [Security](SECURITY.md)
- [Decision records](docs/adr/)

## License
[GPL-3.0-or-later](LICENSE)
