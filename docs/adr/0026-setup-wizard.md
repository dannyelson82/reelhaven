# 0026: A setup wizard for automatic compression

- Status: accepted (scan step amended by ADR-0027)
- Date: 2026-10-08

## Context
Everything needed for automatic compression exists (libraries, languages,
profiles, test runs, watch modes, integrations), but setting it up means
visiting six pages in the right order. The owner wants it dead simple for
inexperienced users. ARCHITECTURE.md §11.2 already sketches a first-run wizard
but the roadmap had no phase for it.

## Decision
- The next phase (**0.7**) is a **setup wizard**; *Insight and safety* moves to
  0.8.
- The wizard opens after the admin account is created (once), **Add library**
  always uses it, and existing libraries get **Set up automatic compression**.
- **Once per server** (skipped when already done): a hardware step (GPU check;
  if none works, a switch to allow CPU encoding so the wizard can still
  finish) and an optional *connect your apps* step (Sonarr/Radarr with webhook
  instructions, Plex).
- **Per library**: folder (name and type guessed), automatic scan, two language
  questions, **three quality cards** (Smallest / Balanced / Best quality, each
  with the estimated saving on that library, Balanced preselected; *More
  options* for mimic and the editor), **one audio question** (keep / shrink
  big tracks, keep surround / stereo only), an automatic **test run** with
  approval, and a final step that switches the library to **Automatic** (or
  *Watch*).
- Every step has a recommended default, plain language, and a way back. The
  wizard only uses features that already exist; the safety rails (verify,
  recycle bin, test-run gate, review flags, pause) are unchanged.
- **Space savings tracking** (owner request, also phase 0.7): the Dashboard shows the
  total saved over the life of the install, this week and this month, and
  weekly and monthly charts, overall and per library. Savings come from the
  before/after sizes every replacing job records; a file restored from the
  recycle bin takes its saving back out. The rest of the stats dashboard
  (per-GPU performance, trends) stays in 0.8.
- When the chosen preset and audio answer don't match a built-in profile, the
  wizard saves a profile named after them (e.g. *Balanced, smaller audio*) and
  reuses it for other libraries with the same answers.

## Consequences
- A new user goes from install to an automatic library in one flow.
- One new backend endpoint estimates savings for several candidate profiles
  without changing anything; the rest is frontend.
