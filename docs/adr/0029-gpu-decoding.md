# 0029: Decode on the GPU too

- Status: accepted
- Date: 2026-10-08

## Context
GPU encodes decoded the source on the CPU and handed raw frames to the card.
On the owner's server six NVENC sessions kept the RTX 3060's encoder at 100 %
while its decoder sat at 1 % and the CPU load was about 30 on 6 cores: the
CPU was doing the decoding (and scaling and pixel-format conversion) for every
job. The owner asked for GPU decoding as the priority.

## Decision
- **NVIDIA first.** When a file is encoded with NVENC and NVDEC can decode it,
  ffmpeg decodes on the same card (`-hwaccel cuda -hwaccel_device N
  -hwaccel_output_format cuda`) and keeps the frames there: scaling and bit
  depth happen in `scale_cuda` (lanczos; `p010le` for 10-bit, `nv12` for
  8-bit). The encoder settings are unchanged.
- **Which files**: H.264 8-bit, HEVC 8/10/12-bit, VP9 8/10/12-bit, AV1 8/10-bit,
  MPEG-2 and VC-1, all 4:2:0. Anything else (H.264 10-bit, 4:2:2, 4:4:4,
  MPEG-4 Part 2) is decoded on the CPU as before. The stream's pixel format is
  now recorded at scan time; files scanned earlier don't have it and are taken
  as 4:2:0.
- **Fallback**: if a GPU-decoded encode fails (a card too old for AV1, a wrong
  guess about an older scan, a driver problem), the same job is retried once
  with CPU decoding. Cancelling is never retried. Test runs use the same path.
- Verification, HDR checks and everything after the encode are unchanged.
- **Intel (QSV) and AMD (VAAPI)** decoding follow in a second step with the same
  fallback.

## Consequences
- Much lower CPU use per GPU job, so the CPU stays free for other containers.
- A file that can't be GPU-decoded costs one quick failed start before the CPU
  retry.
