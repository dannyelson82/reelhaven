# 0003: Use jellyfin-ffmpeg as the encoder

- Status: accepted
- Date: 2026-10-06

## Context
We need NVENC, Intel QSV, VAAPI and AMD support plus HDR handling in one
ffmpeg build that works inside a container. Building ffmpeg ourselves with
all hardware support is slow and fragile.

## Decision
Install the jellyfin-ffmpeg package in the image and call it as an external
program. The binary path is configurable for development.

## Consequences
- Well-tested hardware support maintained by an active project.
- Base image must be a distribution jellyfin-ffmpeg packages for (Debian/Ubuntu).
- Development environments without it can use a static ffmpeg for CPU-only tests.
