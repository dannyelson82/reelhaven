# 0024: Optional downmix to stereo

- Status: accepted
- Date: 2026-10-07

## Context
ADR-0023 converts audio but never changes the channel count, and always copies
Atmos / DTS:X. The owner wants the extra saving of stereo audio (a 2-hour film:
~0.55 GB as E-AC-3 5.1, ~0.14 GB as AAC stereo), accepting that the surround
mix is gone once the original leaves the recycle bin.

## Decision
- Profiles get **Downmix surround to stereo**, **off by default**, available when
  the profile converts audio.
- When on, **every** audio track with more than two channels is converted to
  stereo in the profile's codec at twice the per-channel bitrate, whatever its
  bitrate, **including Atmos and DTS:X** (owner decision: the biggest tracks are
  the point, and stereo can't keep objects anyway). Mono and stereo tracks
  follow ADR-0023's rules. Nothing is ever upmixed.
- The optional extra stereo AAC track isn't added when the main track is
  already downmixed.
- The verifier checks the channel count of downmixed tracks.
- Mimic suggests downmixing (marked *estimated*) when the sample's main audio
  is compact stereo, with a note that surround will be lost.

## Consequences
- Much smaller files for stereo-only households.
- An irreversible loss once the recycle bin entry expires; the editor warns.
- Amends ADR-0023 (object audio is no longer *always* copied).
