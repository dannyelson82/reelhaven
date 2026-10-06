# Phase 0.4: Encoding

Planned with the owner on 2026-10-06. Decisions: ADRs 0019–0020.
Release: **v0.4.0**.

Goal: re-encode video on the owner's NVIDIA and Intel GPUs to save space,
through the same safety pipeline as 0.3 (verify before replacing, recycle bin,
manual apply), gated by a quality-checked test run per library.

Owner hardware: NVIDIA + Intel. The dev environment has no GPU: GPU command
lines are golden-tested here, CPU encoders (x265, SVT-AV1) are tested on real
files, and the owner verifies GPU encodes on the server (Hardware page).

| # | Chunk | Contents |
|---|-------|----------|
| 1 | Design records | ADRs 0019–0020, this plan |
| 2 | Device detection | nvidia-smi, /dev/dri + vainfo, per-device/codec test encodes, Hardware page |
| 3 | Profiles | Profile model + table, built-ins (High quality / Balanced / Small), editor, library profile choice |
| 4 | Command builders | NVENC, QSV, VAAPI, x265, SVT-AV1 (AMF later); quality mapping; HDR10/HLG preserved, DV skipped; resolution cap; audio copy/transcode; golden tests |
| 5 | Planner + skip rules | Encode decision (already efficient, estimated savings < 10 %, DV/unsupported), combined with 0.3 track changes |
| 6 | Encode pipeline | Per-device worker pools, /transcode output → verify (incl. size check) → copy to .reelhaven/work → rename; "no gain" marking |
| 7 | Test run | 1 sample per library (configurable), XPSNR + SSIM, preview clips, gate for bulk encode |
| 8 | Live progress | WebSocket job updates (fps, speed, ETA) |
| 9 | Wrap-up | Docs, release v0.4.0, GPU checklist for the owner |
