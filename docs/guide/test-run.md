---
title: Test run
order: 80
summary: Try a profile on a few files, check the quality, then unlock re-encoding the whole library.
---

# Test run

Re-encoding can't be undone once the originals leave the recycle bin, so
before ReelHaven re-encodes a whole library, you try the profile on a few
files and approve the result. **Originals are never touched by a test run.**

## Start a test run

1. Open the library and go to the **Test run** tab. (The library needs a
   [profile](profiles.md).)
2. Choose **Files to test**: 1 to 5. ReelHaven remembers your choice for the
   library.
3. Click **Start test run**.

ReelHaven picks the files itself: the largest files that would be
re-encoded, mixing resolutions, HDR and different titles where it can. Test
runs go ahead of other queued work, and progress is shown live. The files
are encoded one after the other, so each result appears as soon as it's
ready (the next one shows **up next**) and you can start comparing straight
away.

## Read the results

For each file:

- **Rating**: *Indistinguishable*, *Very good*, *Good* or *Visible loss*,
  based on the measured quality.
- **Size** before → after, and **Saved**. It's red if the saving is below the
  profile's minimum (10 %); a real encode of that file would keep the
  original.
- **Quality**: the measured scores. **XPSNR** (higher is better; around 40 dB
  and above is indistinguishable) and **SSIM** (0 to 1; 0.985 and above
  counts as indistinguishable).
- **Video**: the new codec, bit depth, resolution and HDR type, plus which
  device encoded it and how fast.
- **Clips**: a short scene from both, to [watch them play](#watch-them-play).
- **Still frames**: the original and the re-encode side by side at five
  moments spread through the file, at full resolution (up to 4K) and without
  any compression of their own. Pick a moment with the row of times above
  them. HDR stills are converted to normal colours for the browser, so judge
  HDR colours on your TV.

## Compare full screen

Click a still (or **Compare full screen**) to look closely:

- **Side by side**: the original on the left (on top on a phone), the
  re-encode next to it. One zoom control works for both, and dragging either
  picture moves both, so they always show the same spot. **1:1** shows one
  picture pixel per screen pixel; **Fit** shows the whole picture again.
- **Swipe**: one picture, original on the left of a divider and re-encode on
  the right. Drag the divider across a detail (or select it and use ← →) to
  see what changes.
- Scroll the mouse wheel or pinch to zoom where you point; the times at the
  top switch moments and keep your zoom, so you can check the same spot.
- Keys: ← → switch moments, **+** and **−** zoom, **0** fits, **1** is 1:1,
  **S** switches between side by side and swipe, **Esc** closes.

Look at faces, dark areas, skies and fine texture such as hair or grass;
that's where a smaller file shows first.

### Watch them play

Some problems only show in motion: blocky dark scenes, smeared fast action,
shimmering grain. So each test file also gets two short **clips** of the same
15-second scene from the middle of the file, one from the original and one
from the re-encode. In the full-screen view, switch **Stills** to **Video**
(or press **V**):

- **Play** starts both together; they pause, jump and loop together too. The
  slider moves through the scene and shows where you are in the film.
- Side by side and Swipe, zooming and dragging all work while they play.
- Keys: **Space** plays or pauses, ← → jump a second, **V** goes back to the
  stills.

Browsers can't play most MKV, HEVC or AV1 files, so the clips are converted
to H.264 at a far higher quality than the encode being judged (what you see
is the re-encode, not the clip). They have no sound, and HDR is shown
converted to normal colours. The clips are made on a graphics card when
there is one and take a few seconds; together they use about 20 to 150 MB
per test file in the transcode folder, removed with the test run.

With several files, a summary shows the total saving and the **Weakest
quality**. The re-encoded files of the latest test run stay in
`/transcode/test-run/` if you want to play them on your TV.

## Approve

If you're happy, click **Looks good: allow re-encoding this library**. You
can then apply the [dry run](dry-run.md) to re-encode the whole library.

- Every file must succeed. If any fails, the run can't be approved: read the
  error, fix the cause, and start a new test run.
- Changing the profile (or the library's choice of profile) needs a new
  approved test run.
- Cancelling a test file on the Jobs page fails the run. Test jobs can't be
  retried with **Try again**; start a new test run instead.
- Track-only changes and single files never need a test run.
