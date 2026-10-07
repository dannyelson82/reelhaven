# Phase 0.5: Mimic

Planned with the owner on 2026-10-07. Decisions: ADRs 0022-0023.
Release: **v0.5.0**.

Goal: pick a file you like from a library and get a compression profile that
reproduces its video quality (and, if wanted, its compact audio) across a
whole library.

Owner decisions:
- Samples come from libraries only, no upload (ADR-0022).
- Profiles gain audio re-encoding (E-AC-3 / AAC / Opus at per-channel
  bitrates), with audio-only jobs and the lossy 1.5x rule (ADR-0023).
- Mimic never sets a resolution cap (resolution is always kept).
- Samples without recorded encoder settings get an estimated quality level,
  clearly marked; no target-bitrate mode.

| # | Chunk | Contents |
|---|-------|----------|
| 1 | Design records | ADRs 0022-0023, this plan, ARCHITECTURE/SECURITY updates |
| 2 | Audio in profiles | Profile audio model (copy / E-AC-3 / AAC / Opus + per-channel bitrate), command builder, verifier, which-tracks rules (pure, tested), editor UI, guide |
| 3 | Audio-only jobs | Planner: audio savings estimate and audio-only plans (video copied), dry run and file details show them, end-to-end tests |
| 4 | Sample analysis | Pure functions: read x264/x265 settings strings (CRF, preset, bit depth) and encoder tags; estimate a level from bits per pixel using the 0.4 calibration data; map audio to the nearest profile audio. Tests with fixtures encoded at known settings |
| 5 | Mimic UI | "Mimic a file" on the Profiles page: pick a file, see what was read vs estimated, edit, save (profile source = mimic, report stored); guide page |
| 6 | Wrap-up | Docs, calibration notes for estimation, release v0.5.0 |
