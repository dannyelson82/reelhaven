# 0008: Images built by CI and published to GHCR

- Status: accepted
- Date: 2026-10-06

## Context
The development environment (code-server) has no Docker access, on purpose:
mounting the Docker socket would give root on the host to anything in the
editor.

## Decision
GitHub Actions builds the image and pushes it to
`ghcr.io/dannyelson82/reelhaven`: `edge` from `main`, `X.Y.Z` and `latest`
from version tags. The Unraid template pulls from GHCR.

## Consequences
- No Docker socket anywhere in development.
- Testing a container change means pushing and letting CI build, then
  pulling on Unraid (use the `edge` tag).
