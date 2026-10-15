# 0.9.2: Fixes and reports

Planned with the owner on 2026-10-15 from their testing notes. Decisions:
ADR-0033. Release: **v0.9.2**. Dolby Vision handling waits for failure reports.

| # | Chunk | Contents |
|---|-------|----------|
| 1 | Design records | ADR-0033, this plan, SECURITY.md (Keep me logged in, why a session wasn't recognised) |
| 2 | Opus audio fix | Video quality options were passed without a stream specifier (`-global_quality`, `-qp`, …), so Intel encodes applied them to the audio too and libopus refused to start. Scope every video rate-control option to the video stream |
| 3 | Login | Password-manager friendly form, **Keep me logged in**, log why a page load wasn't logged in |
| 4 | Retry all clears failures | `jobs.cleared_at`; Retry all and Retry clear the failed jobs they replace; Failed tab and count leave them out |
| 5 | Failure report | `jobs.command`; **Download failure report** on the Jobs page |
| 6 | Review report | `review_log` record; **Download review report** on the Review page |
| 7 | Release | Guide, release notes, v0.9.2 |
