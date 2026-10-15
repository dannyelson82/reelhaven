# 0033: Failure and review reports, Retry all clears failures, Keep me logged in

- Status: accepted
- Date: 2026-10-15

## Context
Testing 0.9.1 on the server, the owner hit job failures (Dolby Vision files,
Opus audio) and wanted a way to hand everything ReelHaven knows about them to
Claude in one go, for failures and for every file waiting on the Review page,
without copying items one at a time. Two more problems came up:

- After **Retry all**, the old failed jobs stayed on the Failed tab next to the
  new ones, so it never looked cleared.
- On Safari on an iPhone (over Tailscale, by IP and port) the owner has to log
  in again every time they switch tabs or apps. The server log shows the page
  reloading and the session cookie not being recognised. Sessions are meant to
  last 7 days, so the cookie is being lost or not sent, and the server keeps no
  record of why. The login form also isn't picked up by password managers.

The Review page is computed on demand from the library (ADR-0032), so once a
file leaves it, the reason it was there is gone.

## Decision
- **Two downloadable reports**, plain text so they can be pasted or attached:
  - **Failure report** (Jobs page): every failed job, newest first, including
    ones Retry all has cleared from the Failed tab. For each: the file, the
    ReelHaven version, the device, what the file contained (streams, HDR
    type), the plan, the exact ffmpeg command and the end of its output, and
    the error.
  - **Review report** (Review page): every file on the Review page with why
    it's there and what ReelHaven knows about it (tracks, original language
    and where it came from, the last job's error), plus items resolved in the
    last 90 days.
  - Secrets are redacted with the same filter as the logs. File names and
    paths stay in, because they help diagnose; the owner chooses whom to send
    the report to.
- **The ffmpeg command is stored on the job** (`jobs.command`) when it runs,
  so the report shows what really ran instead of rebuilding it.
- **A review record** (`review_log` table): each (file, kind) the Review page
  finds is recorded with its detail when first seen, updated while it stays,
  and marked resolved when it's gone. Resolved entries are removed after 90
  days. It's updated whenever the review list is computed, so no extra
  background work.
- **Retry all clears failures**: the failed jobs of every file it plans again
  get `cleared_at` set, whether a new job was queued or the file no longer
  needs work. Retrying one job clears that job too. The Failed tab and its
  count leave out cleared jobs; the failure report and the database keep them.
  Cancelled jobs are untouched, as before.
- **Login**:
  - The login form gets the names and attributes password managers look for.
  - **Keep me logged in** (ticked by default): ticked, the cookie lasts the
    idle timeout as now; unticked, it's a browser-session cookie. The server
    side expiry is the same either way.
  - When a page load isn't recognised as logged in, the server logs why: no
    cookie sent, unknown session, or expired session. It never logs the
    cookie itself. This tells us where the iPhone logouts come from.

## Consequences
- Two migrations (`jobs.command` + `jobs.cleared_at`, `review_log`).
- Reports can be large for big libraries; they're generated on request and
  streamed as a download, not kept.
- Failed jobs are never deleted, so the failure report can grow; it covers all
  of them, newest first, and a date range can be added later if needed.
- Dolby Vision handling is decided later, once failure reports show what the
  owner's files are.
