---
title: Stats
order: 92
summary: How each graphics card performs, how many jobs run each day, and how much space you've saved.
---

# Stats

**Stats** (in the menu) shows how your hardware is doing and how much space
ReelHaven has saved.

## Graphics cards and CPU

One card per device that re-encoded files in the chosen period (**7 days**,
**30 days**, **90 days** or **All time**):

| Shown | What it means |
|---|---|
| **Files** | Re-encodes finished, kept or not ("no gain" counts too). |
| **Saved** | Space saved by the files it re-encoded. |
| **Speed** | Hours of video per hour of work: *8.0× real time* re-encodes a 2-hour film in 15 minutes. Running several files at once on one card adds up. |
| **Average** | Frames per second, averaged over the video it encoded. |
| **Video** | Hours of video encoded, and the time it took. |
| **Decoded on GPU** | How many of its encodes also had the original unpacked on the graphics card. Below 100 %, some formats fell back to the CPU (see [Hardware](hardware.md)). |

Failed jobs are counted under the card that ran them.

## Jobs per day

A chart of the last 30 days: files re-encoded, files with only track changes,
and failures.

## Space saved

The same [space saved](jobs.md#space-saved) card as on the Dashboard: total, this week and
this month, per week or month, and per library.

## Kept as is

Files ReelHaven left unchanged on purpose. Nothing to decide; they're listed so
you can see what was kept and why.

- **No gain**: re-encoding, or converting the audio, didn't make the file
  smaller, so the original was kept. It isn't tried again with the same
  settings.
- **Not re-encoded**: Dolby Vision and HDR10+ files, which ReelHaven never
  re-encodes (it would lose their extra picture information). Their languages
  are still handled, and track changes keep the Dolby Vision layer.
