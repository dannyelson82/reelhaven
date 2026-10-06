<p align="center"><img src="assets/icon.png" width="128" alt="ReelHaven icon"></p>

# ReelHaven

**Smaller files. The right language.**

ReelHaven automatically compresses your video library on Unraid using every
GPU you have, keeps only the audio and subtitle languages you want, and keeps
Plex, Jellyfin, Sonarr and Radarr in sync.

> ⚠️ Early development (v0.3). It can now change files, but only when you
> ask it to, and every original goes to a recycle bin first. Try it on a copy
> or a small library before trusting it with media you can't afford to lose.

## What works today (v0.3)
- Libraries: scan your folders and see every file's audio and subtitle tracks
- Original language of each title from Sonarr, Radarr or TMDB (or set by hand)
- Language policy per library, and a **dry run** showing exactly what would change
- **Apply** per file or per library: tracks are removed and defaults fixed by a
  fast remux (no re-encoding), each result is verified before it replaces the
  original, and originals stay in a 14-day recycle bin with one-click restore

## First start
Open the web UI (port 7171) and create the admin account **before** exposing
ReelHaven to the internet: until then, whoever opens it first becomes admin.

## Planned features
- One-click compression profiles, or **mimic** a file you like
- Keep source resolution or cap it; never upscales
- Multi-GPU encoding: NVIDIA NVENC, Intel QuickSync, AMD
- Detects each title's **original language** (Sonarr, Radarr, TMDB) and
  strips unwanted audio and subtitle tracks; English forced subtitles as
  default for English audio
- Finds files that arrived in the wrong language and can quarantine and
  re-download them
- Watches folders and Sonarr/Radarr imports to process new files automatically
- Dry run and test run modes before anything is changed
- Recycle bin for every replaced file
- Stats: files processed, space saved, per-GPU performance

## Documentation
- [Architecture](ARCHITECTURE.md)
- [Security](SECURITY.md)
- [Decision records](docs/adr/)

## License
[GPL-3.0-or-later](LICENSE)
