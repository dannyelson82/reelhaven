---
title: Languages
order: 30
summary: Keep only the audio and subtitle languages you want, based on each title's original language.
---

# Languages

Many files carry audio and subtitles in languages nobody in your home
watches. ReelHaven removes those tracks and keeps the ones you want, including
each title's **original language** (for example Japanese audio for a Japanese
film).

## Original language

ReelHaven looks up the language each movie or series was originally made in:

1. **Sonarr** (series) or **Radarr** (movies), if you've added them on the
   [Integrations](integrations.md) page,
2. otherwise **TMDB**, if you've added a TMDB key,
3. otherwise it stays **unknown**.

You can always set it by hand in a file's details (**Change for every file of
this title**). That applies to every file of the movie or series.

When the original language is unknown, only your wanted languages are kept,
and the dry run says so.

Until the lookup has run, a file is never changed. The lookup happens at the
end of each scan, so new files wait a little; if Sonarr, Radarr or TMDB
couldn't be reached, those files wait for the next scan. The dry run shows
how many are waiting. This keeps an original-language soundtrack (say, the
Japanese audio of an anime) from being removed just because the language
wasn't known yet.

## Language policy

Each library has its own policy. Open the library and click **Language
policy**. Nothing changes until you apply a [dry run](dry-run.md).

| Setting | Default | What it does |
|---|---|---|
| **Languages you want** | English | Audio and subtitles in these languages are kept. The **first** one is your own language: it decides which subtitles play by default. |
| **Also keep each title's original language** | On | Keeps original-language audio and subtitles too. |
| **Subtitles to keep**: **Full**, **Forced**, **SDH / hearing impaired** | All on | Which kinds of subtitles to keep in your wanted languages. |
| **Keep commentary tracks** | On | Director's commentary and similar audio. |
| **Tracks without a language tag** | Always keep them | Keep untagged tracks (safest), or treat them as a language you choose. |
| **Set the default audio and subtitle tracks** | On | Original-language audio plays by default. Your language's forced subtitles are on by default, or full subtitles when the audio is foreign. |
| **Files with none of your languages** | Flag for review | What happens to a *wrong language* file (an English film with only Spanish audio, say: probably the wrong release). **Flag for review** changes nothing and lists it on the [Review](review.md) page. **Quarantine** or **Delete** moves it out of the library and asks Sonarr/Radarr to blocklist that release and search for another; see [Wrong-language files](#wrong-language-files). |
| **Show my language's subtitles automatically** | On | Also marks that default subtitle as **forced**, so Plex and other players show it without you switching it on: forced subtitles for the foreign lines in a film in your language, or the full subtitles for a film in another language (say, a Japanese film). Only subtitles in your own language are marked. Files ReelHaven already processed are picked up by the next scan as a quick flag change (no re-encode). |

## Safety rules

- ReelHaven **never removes the last audio track**. If a file has no audio in
  a language you want, all audio is kept and the file is flagged **Wrong
  language** or **No wanted audio**. Flagged files are left untouched for you
  to review.
- Tracks without a language tag never make a file count as *wrong language*.
- Only *wrong language* files can be quarantined or deleted automatically:
  the title's original language is known and none of the audio is untagged.
  *No wanted audio* files (original language unknown, or untagged audio)
  always wait for you.
- Language codes are matched however they're written (`fre`, `fra` and `fr`
  are all French).
- A track-only change (**Remux**) keeps the same container (MKV stays MKV)
  and the same track order, plus chapters and attached fonts. The file name
  doesn't change.

## Wrong-language files

With **Quarantine** or **Delete** chosen, an [Automatic](automation.md)
library handles wrong-language files by itself, a few at a time like any other
job. In any library you can also do it for one file from the
[Review](review.md) page (**Quarantine** or **Delete**, after you confirm).

1. The file leaves the library for its hidden `.reelhaven` folder, on the same
   disk, so it isn't copied.
2. Sonarr or Radarr (whichever manages the file) is asked to mark the download
   that brought it as failed, which **blocklists that release**, and to
   **search for another**. If it was added by hand (no download to blocklist),
   it just searches. The job on the [Jobs](jobs.md) page says what each one
   answered.
3. The file is kept for the recycle bin's **days to keep** (see
   [Recycle bin](recycle-bin.md)): quarantined files on the **Quarantine** tab,
   deleted ones in the recycle bin. Either can be restored until then. With the
   recycle bin **Off**, the file is removed straight away.

Without Sonarr or Radarr, the file is still moved aside, but nothing searches
for a replacement.

