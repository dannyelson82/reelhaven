---
title: Developer options
order: 120
summary: Download reports about failures and files waiting for review, to send when asking for help.
---

# Developer options

**Settings → Developer** has one switch, **Developer options** (off by
default). Turn it on when you want to send someone everything ReelHaven knows
about a problem.

With it on:

- The **Jobs** page's **Failed** tab shows **Download failure report**: every
  failed job, including ones a retry has cleared from the tab. See
  [Jobs](jobs.md#failure-report).
- The **Jobs** page's **In progress** tab shows **Move waiting jobs back to
  Upcoming**, which empties the queue of jobs in Automatic libraries that haven't
  started, so the automatic queue takes them again in order. See
  [Jobs](jobs.md).
- The **Review** page shows **Download review report**: every file waiting
  for a decision, with why it's there, its tracks, its original language and
  where that came from, and the last job's error, plus everything resolved in
  the last 90 days. See [Review](review.md).
- Both report buttons are also on the **Developer** page.

The reports are plain text files. Passwords and API keys are removed; file and
folder names stay in, because they help work out what went wrong.

Turning the switch off only hides the buttons. Nothing is deleted.
