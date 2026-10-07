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
runs go ahead of other queued work, and progress is shown live.

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
- **Still frames**: the original and the re-encode side by side at up to
  three moments. HDR stills look washed out in a browser; judge colours on
  your TV.

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
