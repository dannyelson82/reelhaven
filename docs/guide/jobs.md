---
title: Jobs and the dashboard
order: 90
summary: Follow the work queue live, cancel or retry jobs, and understand the results.
---

# Jobs and the dashboard

Every file ReelHaven processes is a **job**. The **Jobs** page lists them;
**In progress**, **Failed** and **Done** filter the list.

## How a job works

1. The new file is written to a work area. For a re-encode that's
   `/transcode`, then it's copied next to the library.
2. It's **checked**: it must open and decode, have exactly the planned tracks
   and default flags and the right length, and (for a re-encode) have the
   planned codec and resolution and be smaller than the original.
3. Only then does it replace the original, which goes to the
   [recycle bin](recycle-bin.md).
4. If the original changed after it was planned, the job stops and nothing is
   replaced.

## Statuses

| Status | Meaning |
|---|---|
| **Waiting** | Queued, waiting for a free device. |
| **Working** | Being processed. Shows progress, device, fps, speed and time left. |
| **Checking** | The new file is being verified. |
| **Done** | Finished. Shows the space saved. |
| **Failed** | Something went wrong. **The original file was not changed.** The error says why. |
| **Cancelled** | You cancelled it. |

**Cancel** stops a waiting or running job. **Try again** plans the file again
(it may have changed) and queues a new job.

## No gain

Sometimes a re-encode isn't smaller enough to be worth it. Then the original
is kept, the job shows **No gain: the original was kept**, and ReelHaven won't
try that profile on that file again.

## Live progress

The Jobs page, the Test run tab and the Dashboard update live while you
watch: progress, frames per second, speed (× real time) and an estimate of
the time left, which appears a few seconds into each job. The **Jobs** menu
item shows how many jobs are in progress.

If you use ReelHaven without logging in (local network access, see
[Security](security.md)), pages still update, just every few seconds instead
of instantly.

## Dashboard

The **Dashboard** shows what's being processed right now and how many files
are waiting. Statistics (space saved over time, per-device speed) arrive in a
later version.
