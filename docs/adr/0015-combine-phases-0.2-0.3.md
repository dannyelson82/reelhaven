# 0015: Phases 0.2 and 0.3 ship together

- Status: accepted
- Date: 2026-10-06

## Context
Phase 0.2 (see the library) is only useful once phase 0.3 (languages) acts
on what it shows. The owner asked to build both in one run.

## Decision
Build 0.2 and 0.3 as one phase, planned in `docs/plans/phase-0.2-0.3.md`,
released as **v0.3.0**. Changes to files stay **manual-only**: per file, or per
library after a confirmation that shows how many files will change.
Automatic processing still waits for test runs (phase 0.4). Wrong-language
files are only flagged; quarantine stays in 0.7.

## Consequences
- One larger release instead of two; each chunk is still its own pull request.
- Bulk apply exists before test runs, so it must always go through the
  recycle bin and the audit log and require explicit confirmation.
