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

## Safety rules

- ReelHaven **never removes the last audio track**. If a file has no audio in
  a language you want, all audio is kept and the file is flagged **Wrong
  language** or **No wanted audio**. Flagged files are left untouched for you
  to review.
- Tracks without a language tag never make a file count as *wrong language*.
- Language codes are matched however they're written (`fre`, `fra` and `fr`
  are all French).
- A track-only change (**Remux**) keeps the same container (MKV stays MKV)
  and the same track order, plus chapters and attached fonts. The file name
  doesn't change.
