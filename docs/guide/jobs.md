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

**Pause all processing** (top of the Jobs page and the Dashboard) stops new
jobs from starting; running jobs finish. **Resume processing** carries on.
Jobs started by an [Automatic](automation.md) library show *requested by
automatic*.

## Upcoming

An Automatic library keeps only a few jobs waiting at a time (enough to keep
every graphics card and worker busy) and adds the next ones as jobs finish.
**Upcoming** shows the rest: every file that still needs work but isn't queued
yet, in the order it will run, with what will happen to it and roughly how
much it saves. Each file says why it's waiting:

| Badge | Meaning |
|---|---|
| **Next** | Queued automatically as workers free up. |
| **Waiting for a test run** | A re-encode in a library whose profile hasn't passed a [test run](test-run.md) yet. |
| **Not automatic** | The library isn't set to Automatic: apply its [dry run](dry-run.md) to queue these. |

Files waiting for their original language, and files whose last job failed,
are on the [Review](review.md) page instead.

## No gain

Sometimes a re-encode isn't smaller enough to be worth it. Then the original
is kept, the job shows **No gain: the original was kept**, and ReelHaven won't
try that profile on that file again.

The same goes for converting audio: if a soundtrack would come out bigger (a
very efficient lossless track, for example), ReelHaven doesn't convert it and
won't try that conversion on that file again. Anything else the job was going
to do, such as removing unwanted languages or fixing the default and forced
subtitle flags, is still done straight away. If the conversion was the only
change, the original is kept and the job shows **No gain**.
## Live progress

The Jobs page, the Test run tab and the Dashboard update live while you
watch: progress, frames per second, speed (× real time) and an estimate of
the time left, which appears a few seconds into each job. The **Jobs** menu
item shows how many jobs are in progress.

Each re-encode also shows which device encodes it and whether the original
video was **Decoded on GPU** or **Decoded on CPU** (see
[Hardware](hardware.md#decoding-on-the-gpu-too)). If a file can't be decoded on
the graphics card, the job switches to the CPU by itself and the label follows.

If you use ReelHaven without logging in (local network access, see
[Security](security.md)), pages still update, just every few seconds instead
of instantly.

## Dashboard

The **Dashboard** shows what's being processed right now and how many files
are waiting, and how much space ReelHaven has saved.

### Space saved

Once the first file has been made smaller, the **Space saved** card shows:

- **Since you installed ReelHaven**: the total space saved over the life of
  this install.
- **This week** and **This month**: what was saved in the current calendar
  week (starting Monday) and month, in the server's local time.
- **Files made smaller**: how many files were replaced by a smaller version.
- A bar chart of the last 12 weeks or 12 months (switch with **Weekly** /
  **Monthly**). Hover over a bar for the exact figure, or choose **Show as
  table** to see the numbers as a list.
- **By library**: the totals for each library, when you have more than one.

The figures follow the recycle bin. If you restore an original, its saving is
taken back out (in the week you restored it); if you later put the smaller
version back, the saving counts again. Files that were only remuxed (for
example, unwanted languages removed) count too, since they also got smaller.
