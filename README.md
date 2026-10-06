<p align="center"><img src="assets/icon.png" width="128" alt="ReelHaven icon"></p>

# ReelHaven

**Smaller files. The right language.**

ReelHaven automatically compresses your video library on Unraid using every
GPU you have, keeps only the audio and subtitle languages you want, and keeps
Plex, Jellyfin, Sonarr and Radarr in sync.

> ⚠️ Early development. No releases yet. Do not point it at media you can't
> afford to lose.

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
