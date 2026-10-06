# 0020: Encode test run gates bulk encoding

- Status: accepted
- Date: 2026-10-06

## Context
Re-encoding is lossy and slow; a wrong profile applied to a whole library is
expensive to undo. The owner wants to "re-encode one file and check quality"
before encoding a library.

## Decision
- A **test run** encodes **one** sample file per library by default (1–5
  configurable) into `/transcode/test-run/<library>/`. Originals are untouched.
- Quality is measured automatically: **XPSNR** (perceptually weighted) and
  **SSIM** against the source (jellyfin-ffmpeg has no libvmaf), shown with a
  plain-language rating, plus size before/after and a short side-by-side preview.
- **Bulk encode** for a library is allowed only after a passed test run with the
  library's *current* profile; changing the profile requires a new test run.
  Single files can always be encoded manually. Remux-only changes (0.3) are not
  gated.

## Consequences
- One extra step per library before bulk encoding, in exchange for confidence.
- The quality numbers are guidance, not a guarantee; the preview lets the owner judge.
