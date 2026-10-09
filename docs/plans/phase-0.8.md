# Phase 0.8: Compare and tune

Planned with the owner on 2026-10-09. Decisions: ADR-0031.
Release: **v0.8.0** (one release at the end). *Insight and safety* moves to 0.9.

Goal: make it easy to *see* what a setting does before trusting it with a
library, and to find the smallest files that still look right.

Owner decisions: side-by-side viewer with synced zoom and pan, plus a swipe
mode; watching in the browser through short near-lossless comparison clips;
Mimic inside the wizard; "find my sweet spot" with three sizes and dialling in,
using library files first or downloadable open-licence test films; audio bitrate
guidance with the Plex note; one release at the end.

| # | Chunk | Contents |
|---|-------|----------|
| 1 | Design records | ADR-0031, this plan, roadmap |
| 2 | Comparison viewer | Full-screen stills viewer: side by side (one zoom control, synced drag-to-pan) and swipe; keyboard and touch; in *Try it* and on the Test run tab; more and sharper stills |
| 3 | Audio guidance | Per-format bitrate table ("what you'll hear") in the profile editor and the wizard's audio step; Plex note; guide |
| 4 | Mimic in the wizard | *Copy a file I like* in the size-and-quality step: pick a library file, see what was read and the estimated saving, choose it |
| 5 | Comparison clips | Same 10–20 s scene from original and new file per test-run sample, near-lossless H.264 MP4 (HDR tone-mapped, GPU where possible), served with seeking; cleaned up with the run |
| 6 | Synced players | Two videos playing, pausing and seeking together; side by side or swipe; full screen |
| 7 | Sweet-spot sessions (backend) | Half-step profile quality; a session = one source scene encoded at three sizes, then any step lower, higher or in between; per step: estimated full-file size, quality rating, stills, clips; save as profile |
| 8 | Test films | Catalogue of open-licence films with licence and source; download on request (progress, checksum), stored in appdata, delete |
| 9 | Find my sweet spot (UI) | Pick a file (library first) or a test film, compare the three steps with the viewer and players, dial in, save; entry from Profiles and the wizard |
| 10 | Wrap-up | Guide, release v0.8.0 |
