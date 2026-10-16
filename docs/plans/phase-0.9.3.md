# 0.9.3: Fewer things to review

Planned with the owner on 2026-10-16 from their review report. Decisions:
ADR-0034 (Dolby Vision track changes), ADR-0035, ADR-0036. Release: **v0.9.3**.
Done: #108–#114 and the release.

Owner decisions: build ideas 1–4 from the review analysis; quarantine follows
the recycle bin (current behaviour); TV and Movies both use Quarantine for wrong
language and damaged files. The owner sets this in each library's settings.

| # | Chunk | Contents |
|---|-------|----------|
| 1 | Already merged | #108 cover-art encodes, #109 Dolby Vision track changes (ADR-0034), #110 stale failures cleared |
| 2 | Design records | ADR-0035, this plan |
| 3 | Planner fixes | Commentary-only wanted audio counts as main audio; stale audio bitrate tags ignored |
| 4 | Kept as is | No gain and Not re-encoded leave the Review page for Stats → Kept as is |
| 5 | Damaged files | Unreadable for 24 hours → the library's wrong-language action (quarantine + re-search) |
| 5b | Colour check | ADR-0036: green/purple Dolby Vision 5 damage (owner request, FileFlows re-encodes), same swap |
| 6 | Release | Guide, release notes, v0.9.3 |
