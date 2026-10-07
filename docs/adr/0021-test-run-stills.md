# 0021: Test run previews are still frames

- Status: accepted
- Date: 2026-10-07

## Context
ADR-0020 promised a short side-by-side preview clip. Test encodes are usually
10-bit HEVC or AV1, which many browsers cannot play, so a clip in the web UI
would often show nothing.

## Decision
A test run shows **still frames** instead: the original and the re-encode side
by side, taken from the middle of each segment that is quality-measured
(up to three per file), scaled to 1280 px wide JPEGs. Only the latest test
run per library is kept on disk. The rest of ADR-0020 stands.

## Consequences
- Previews work in any browser and cost little disk space.
- Motion artefacts (banding in fades, smearing) don't show in stills; the
  XPSNR/SSIM numbers cover them, and the owner can play the re-encode from
  `/transcode/test-run/` on a TV.
- HDR stills look washed out in a browser; the UI says so.
