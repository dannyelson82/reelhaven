# 0016: Recycle bin and work folder inside each library

- Status: accepted
- Date: 2026-10-06

## Context
ARCHITECTURE.md placed the recycle bin at `/media/.reelhaven/recycle`. Users
may map several host folders under `/media`; if a library is a separate mount,
moving an original into that folder becomes a slow full copy. Writing remux
output to `/transcode` and then moving it into the library has the same
problem, and a copy interrupted half-way must never leave a broken file in
place.

## Decision
Each library gets a hidden **`.reelhaven/`** folder at its root:
- `.reelhaven/recycle/<job id>/<relative path>`: replaced originals
- `.reelhaven/work/`: remux output while it is written and verified

Both are on the library's own filesystem, so every move is a `rename`. The
replacer checks that source and destination are on the same device
(`st_dev`); if not, it refuses rather than copying. `/transcode` is
reserved for GPU encodes (phase 0.4), whose output is first copied into
`.reelhaven/work/` and only then renamed into place.

The scanner and file browser ignore `.reelhaven` folders.

## Consequences
- Moves and restores are instant and atomic.
- Each library root needs write access (it already needs it to replace files).
- Plex and Jellyfin skip hidden folders; this is noted in the docs in case a
  setup shows recycled files.
