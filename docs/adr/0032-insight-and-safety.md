# 0032: Insight and safety (phase 0.9); no two-factor login

- Status: accepted
- Date: 2026-10-09

## Context
Phase 0.9 was planned as the rest of the stats dashboard, a review page,
wrong-language quarantine with re-search, optional TOTP two-factor login and an
audit log page. Planning it, the owner pointed out that ReelHaven is a tool for
the home network: two-factor login adds setup and recovery burden for little
gain there, and can be added later if it turns out to be needed.

## Decision
- **No two-factor login.** TOTP is removed from the roadmap and from
  SECURITY.md. The unused `users.totp_secret` / `totp_enabled` columns stay
  (dropping them gains nothing and a future 2FA could use them). Login stays
  password + sessions, the local-address bypass and the API key.
- **Phase 0.9 = Review page, wrong-language actions, stats.** One release at
  the end (0.9.0). The audit log page moves to 1.0 hardening.
- **Review page**: one place for every file that needs a decision: wrong
  language, no wanted audio, Dolby Vision / HDR10+ skipped, unreadable, waiting
  for its language, last job failed, "no gain". Each kind with its actions
  (try again, ignore, quarantine, delete, open in the library). *Ignore* is
  remembered per file until the file changes.
- **Wrong-language action per library**: **Flag** (default, nothing changes),
  **Quarantine** or **Delete**, as ARCHITECTURE §8.4 planned.
  - *Quarantine* moves the file to the library's own `.reelhaven/quarantine`
    folder (same filesystem, so a rename), then tells Sonarr/Radarr to
    blocklist that release and search for another. Quarantined files are kept
    for the recycle bin's **days to keep** (Off removes them at once after the
    re-search request) and can be restored or deleted from a Quarantine tab.
  - *Delete* is an explicit opt-in with a warning; the file still goes through
    the recycle bin, and Sonarr/Radarr are asked to search again.
  - Both act only on files whose original language is known and whose audio
    has none of the library's languages (untagged audio never counts,
    ADR-0017), and both happen as queued jobs, never during a scan.
- **Stats**: per-device performance (files, hours of video, average fps,
  GPU vs CPU decoding, failures) and trends (savings and files per week,
  queue throughput), on the Dashboard and a Stats page.

## Consequences
- SECURITY.md loses the 2FA section; the local-address bypass rule that
  depended on it ("cannot be enabled while 2FA is on") goes with it.
- Wrong-language Quarantine and Delete change files without a per-file click,
  so they are off by default and the library page says what they will do.
