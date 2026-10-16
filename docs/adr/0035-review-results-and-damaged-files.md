# 0035: Results leave the Review page; damaged files are swapped out like wrong-language ones

- Status: accepted
- Date: 2026-10-16

## Context
The owner's review report (ADR-0033) listed 433 files. 331 of them were results,
not decisions: 195 "no gain" (re-encoding or the audio conversion saved too
little, so the original was kept) and 136 Dolby Vision files that are never
re-encoded. The rest:
- 95 were waiting for a language lookup because Sonarr was rejecting the API key.
- 3 wrong-language files were real (Swedish and French releases of English
  shows).
- 1 was a false alarm: the movie's only English audio track is tagged
  commentary.
- 3 files were damaged: two start with blank data, one is 637 KB.

The report also showed that 40 of the 41 audio "no gain" files carried audio
bitrate tags higher than the whole file's bitrate. These are stale tags left by an
earlier tool. ReelHaven trusted them and converted audio for nothing. Video tags
were already checked this way (#66).

The owner wants language problems and damaged files handled without them:
Sonarr/Radarr download another release, and ReelHaven processes it as usual.

## Decision
- **Results move off the Review page.** "No gain" and "Not re-encoded" (Dolby
  Vision / HDR10+) are no longer Review tabs or counted in the menu. They are
  listed under **Stats → Kept as is**. Review keeps what needs a decision: wrong
  language, failed, unreadable and waiting. The review report still includes
  everything.
- **Commentary-only audio:** when no audio track in a wanted language is main
  audio, a wanted-language track tagged commentary counts as main audio. A file
  whose only English track is mis-tagged is not "wrong language".
- **Stale audio bitrate tags:** an audio track's bitrate tag is ignored when it
  is higher than the whole file's bitrate, or when all the tracks' tags add up to
  more than the whole file. A lossy track with no believable bitrate isn't
  converted.
- **Damaged files:** a file that can't be read, and whose modification time is
  more than 24 hours old (so it isn't still being copied), gets the library's
  wrong-language action. With Quarantine or Delete it's moved aside and
  Sonarr/Radarr are asked to blocklist the release and search for another, as in
  ADR-0032. With Flag (the default), nothing changes. In Automatic libraries the
  replacement is then processed like any new file.
- Quarantined files follow the recycle bin's days to keep, as in ADR-0032. The
  owner chose this, and their bin is off, so the old file is removed once the new
  search has been requested.

## Consequences
- The Review page shows only things to act on. The menu count drops from
  hundreds to a handful.
- A damaged file can be swapped automatically, but only after 24 hours and only
  where the library opted in.
- The Sonarr/Radarr re-search (built from the API specs) is exercised for real
  for the first time. Its results are in the job details and the log.
