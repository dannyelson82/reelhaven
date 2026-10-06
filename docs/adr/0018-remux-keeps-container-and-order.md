# 0018: Remux keeps the container and track order

- Status: accepted
- Date: 2026-10-06

## Context
Phase 0.3 remuxes files to drop unwanted tracks and fix default flags. Changing
the container (e.g. MP4 to MKV) renames the file, which Sonarr, Radarr and
Plex then have to rediscover.

## Decision
- A remux writes the **same container** as its input (MKV stays MKV, MP4 stays
  MP4), so the filename never changes in this phase.
- Kept streams keep their **original relative order**; only removals,
  default flags and the ReelHaven marker tag change.
- Subtitle formats an MP4 can't hold are never introduced (nothing is
  converted in a remux).
- Attachments (fonts) and chapters are kept.

## Consequences
- No renames to propagate until profiles add container choice (phase 0.4).
- A track a player shows first might not be the default; players follow the
  default flag, so this is acceptable.
