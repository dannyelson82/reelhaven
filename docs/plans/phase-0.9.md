# Phase 0.9: Insight and safety

Planned with the owner on 2026-10-09. Decisions: ADR-0032.
Release: **v0.9.0** (one release at the end). Done: #88–#91 and the release.

Owner decisions: review page, wrong-language quarantine with re-search, per-GPU
stats and trends; wrong-language actions Flag, Quarantine or Delete;
quarantine kept like the recycle bin; one release at the end; **no two-factor
login** (removed from the roadmap; can be added later if needed). The audit
log page moves to 1.0.

| # | Chunk | Contents |
|---|-------|----------|
| 1 | Design records | ADR-0032, this plan, roadmap, SECURITY.md (2FA removed) |
| 2 | Review (backend) | Files needing a decision across libraries, by kind, with counts; per-file *ignore* remembered until the file changes |
| 3 | Review page | Tabs by kind, actions (try again, ignore, open in library), counts in the menu |
| 4 | Quarantine | `.reelhaven/quarantine` per library, quarantine jobs, kept for the recycle bin's days, restore and delete; Quarantine tab on the Recycle bin page |
| 5 | Wrong-language actions | Per-library Flag / Quarantine / Delete (with warning); Sonarr/Radarr blocklist + search again; actions on the review page |
| 6 | Stats (backend) | Per-device performance and weekly trends from job results |
| 7 | Stats page | Per-GPU cards and charts; Dashboard summary |
| 8 | Wrap-up | Guide, release v0.9.0 |
