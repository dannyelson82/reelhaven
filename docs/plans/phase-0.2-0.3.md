# Phase 0.2 + 0.3: Library and languages

Planned with the owner on 2026-10-06 (ADR-0015). Decisions: ADRs 0015–0018.
Release: **v0.3.0**.

Goal: add a library and see every file's streams. ReelHaven finds each
title's original language and shows a dry run of track changes. On request,
per file or per library, it remuxes files. Each result is verified first,
and every original goes to a restorable recycle bin.

Owner decisions: recycle bin inside each library (ADR-0016); remux keeps the
container (ADR-0018); apply per file and per library with confirmation;
Sonarr and Radarr tested first (TMDB built but optional).

Each chunk is one pull request off `main`; CI must pass before merge.

| # | Chunk | Contents |
|---|-------|----------|
| 1 | Design records | ADRs 0015–0018, this plan, doc updates |
| 2 | Libraries + file browser | `libraries` table, `/media`-confined path resolution (symlinks resolved first), library CRUD API + UI, folder picker |
| 3 | Probe | ffprobe runner (argument list, `file:` prefix, timeout), `MediaInfo` model, language-code normalisation, HDR/DV detection, disposition flags; tests on generated fixtures |
| 4 | Scanner + library view | Background scan with progress, fingerprint (size + mtime + first/last 64 KiB), probe cache, write-stability check, ignore patterns, `media_files` table, library page with stream details |
| 5 | Integrations | Secret encryption (`/config/secret.key`, per SECURITY.md), `integrations` table holding each service's encrypted key (no separate `secrets` table: every key belongs to one integration), Sonarr/Radarr/TMDB clients, test-connection, path mappings, settings UI |
| 6 | Language resolver | Sonarr/Radarr → TMDB → unknown; per-title cache; manual override |
| 7 | Policy + planner | Per-library language policy; pure planner with exhaustive tests; wrong-language flag |
| 8 | Dry run | Per-library report: counts, estimated savings, track changes, flags |
| 9 | Remux pipeline | `jobs`/`job_results`/`recycle_bin` tables, job queue + CPU worker pool, remux command builder (golden tests), verifier, replacer, recycle bin restore/purge, jobs page, apply per file / per library with confirmation, audit |
| 10 | Wrap-up | Docs, CLAUDE.md, release v0.3.0 |

## Planner decisions (chunk 7)
- Files flagged *wrong language* or *no wanted audio* are left completely
  untouched (no subtitle removal either) for the owner to review.
- If the default audio is untagged, subtitle default flags are left as they are.
- Dolby Vision files may be remuxed (stream copy keeps the DV metadata); the
  verifier checks the output still reports Dolby Vision.
- Subtitle toggles (full / forced / SDH) apply to every wanted language; the
  first wanted language is the viewer's and drives the default subtitle.
- Image subtitles (PGS, VobSub) follow the same language rules; never converted.

## Remux pipeline decisions (chunk 9)
- Remux supports MKV, MP4, M4V and MOV in this version; other containers are
  never queued.
- MP4/MOV can't store "no default track" (the muxer enables the first one),
  so the planner plans for that; otherwise every remux would re-plan itself.
- Restore never deletes: the file currently in place is moved to the recycle
  bin first ("restore-swap").
- A library apply must quote the exact number of files from the dry run; if
  the library changed meanwhile nothing is queued.
