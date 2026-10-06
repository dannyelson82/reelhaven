# 0017: Untagged audio and subtitle tracks

- Status: accepted
- Date: 2026-10-06

## Context
A track's language can be `und`, missing entirely, or (per the Matroska spec)
implicitly English when the Language element is absent. ffprobe reports
both a missing tag and `und` as *no tag*, so ReelHaven cannot tell them apart.

## Decision
- A missing tag and `und`/`zxx`/`mis`/`mul` are all treated as **untagged**.
- The default policy **keeps** untagged tracks (configurable per library:
  keep, or treat as a chosen language).
- Untagged audio counts as "possibly wanted": it **never triggers
  wrong-language detection**, and a file whose audio is all untagged is never
  stripped of audio.
- Language codes are normalised (`fre`/`fra`/`fr` become one language) before
  any comparison.

## Consequences
- Safe default: no track is removed because of missing metadata.
- Badly tagged files are kept as they are rather than "fixed" by guessing.
