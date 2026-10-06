# 0007: Sources for the original production language

- Status: accepted
- Date: 2026-10-06

## Context
Track stripping and wrong-language detection depend on knowing the language
a title was originally produced in. File metadata is unreliable.

## Decision
Resolve in order: Sonarr/Radarr API (when the library is linked) → TMDB
(user-supplied API key; IDs in names first, then title + year) → unknown.
Cache per title; allow manual override.

## Consequences
- Accurate for *arr-managed libraries, good for others.
- Unknown originals disable original-language rules and wrong-language
  detection for that file rather than guessing.
