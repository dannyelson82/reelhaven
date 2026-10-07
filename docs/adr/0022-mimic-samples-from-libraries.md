# 0022: Mimic samples come from libraries only

- Status: accepted
- Date: 2026-10-07

## Context
ARCHITECTURE.md §7.2 planned two ways to give ReelHaven a sample to mimic:
pick a file from a library, or drag one in from the browser (only its first
64 MiB uploaded). The upload path needs its own size limits, temp storage and
cleanup (SECURITY.md), and fails for MP4s whose index is at the end. The owner
keeps the files they'd mimic on the server.

## Decision
Mimic samples are chosen **only from files under the configured libraries**,
through the existing file browser and path checks. There is no upload
endpoint.

## Consequences
- No upload attack surface; the SECURITY.md upload rule is dropped.
- To mimic a file from another computer, the user copies it into a library
  folder first.
- Reading the whole file is possible, so overall bitrate and the encoder
  settings string are always available.
