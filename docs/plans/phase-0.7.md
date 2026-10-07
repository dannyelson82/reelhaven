# Phase 0.7: Setup wizard

Planned with the owner on 2026-10-08. Decisions: ADR-0026.
Release: **v0.7.0**. (*Insight and safety* moves to 0.8.)

Goal: an inexperienced user sets up automatic compression of a library in one
guided flow, with a recommended answer at every step.

Owner decisions: first run + every new library (+ a button on existing
libraries); three quality cards with real estimates; one audio question; extra
steps for GPU check, languages, Sonarr/Radarr and Plex.

| # | Chunk | Contents |
|---|-------|----------|
| 1 | Design records | ADR-0026, this plan, roadmap |
| 2 | Backend support | Savings estimate for candidate profiles (no changes saved), onboarding state (wizard seen / server steps done), tests |
| 3 | Wizard shell + library steps | Route and stepper, first-run redirect, **Add library** and **Set up automatic compression** entry points; folder (guessed name/type), scan, languages |
| 4 | Quality + audio | Three cards with estimates, *More options* (mimic / editor), audio question, find-or-create the matching profile |
| 5 | Try it + go automatic | Automatic 2-file test run with approval, retry with another setting, summary, Automatic / Watch, done screen |
| 6 | Server steps | Hardware (GPU check, CPU fallback switch), connect apps (Sonarr/Radarr + webhook steps, Plex), skipped when done |
| 7 | Wrap-up | Guide, release v0.7.0 |
