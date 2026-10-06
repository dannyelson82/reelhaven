# 0009: Debian 13 base image and Python 3.13

- Status: accepted
- Date: 2026-10-06

## Context
ADR-0002 sets Python 3.12+ and ADR-0003 needs a distribution jellyfin-ffmpeg
packages for. Debian 12's system Python is 3.11, below our minimum.

## Decision
The runtime image is based on **Debian 13 (trixie) slim** with its system
**Python 3.13**. Development uses the same version through uv
(`backend/.python-version`). `requires-python = ">=3.13"`.

## Consequences
- Same distribution family as Jellyfin's own image; jellyfin-ffmpeg and the
  Intel/AMD VA-API drivers are packaged for it.
- One Python version everywhere; no separately downloaded interpreter in the image.
- Moving to a newer Python is a deliberate change (new ADR), not drift.
