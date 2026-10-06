# 0013: First-run admin creation without a setup code

- Status: accepted
- Date: 2026-10-06

## Context
On first start there are no users. Whoever opens the setup page first creates
the admin account. A one-time code printed in the container log would prevent
someone else claiming it first, but adds a step for every user.

## Decision
No setup code (the owner's choice, matching Sonarr and Radarr). Safeguards:
- The setup endpoint works only while **zero users exist**, checked and
  inserted in one transaction, so two simultaneous attempts can't both succeed.
- Admin creation is written to the audit log.
- Until setup is complete, every page except setup and `/healthz` redirects
  to setup, and the API returns `409 setup_required`.
- The README and the Unraid template say to finish setup before exposing
  ReelHaven to the internet.

## Consequences
- Simplest first run.
- A ReelHaven exposed to the internet before setup could be claimed by a
  stranger. Documented, not prevented. A setup code can be added later by a
  new ADR.
