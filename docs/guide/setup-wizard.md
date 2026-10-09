---
title: Setup wizard
order: 15
summary: The easiest way to set up a library: answer a few questions and ReelHaven does the rest.
---

# Setup wizard

The setup wizard takes a library from "just added" to "looked after
automatically" in a few minutes. Every step has a recommended answer already
chosen: if you're not sure, just click **Next**.

You'll find it:

- on your first visit after creating your account (it opens by itself once),
- behind **Add library** on the Libraries page,
- as **Set up automatic compression** on any library's page,
- as **Set up your first library** on the Dashboard while you have none.

## First time only: hardware and apps

The first time, the wizard starts with two steps about the server itself:

- **Hardware**: which graphics cards ReelHaven can use (it tries a short test
  encode on each). If none works, it explains how to give the container your
  GPU, and offers **Allow CPU encoding (slow)** so you can carry on anyway.
- **Your apps**: **Add** Sonarr, Radarr or Plex if you use them (optional;
  see [Integrations](integrations.md)). Once Sonarr or Radarr is connected you
  can also open the webhook instructions for instant new-file notices.
  **Skip** if you don't use them.

Later runs go straight to the library steps.

## The library steps

1. **Folder**: pick the folder that holds the videos. ReelHaven guesses a
   name and whether it's movies or TV shows from the folder name; change them
   if they're wrong. Nothing is changed yet.
2. **Read files**: ReelHaven reads every file to see its picture, sound and
   subtitles. You don't have to wait for it: once the files have been found,
   **Next** unlocks and reading carries on in the background. (A first read
   takes a few minutes for a few thousand films, up to an hour for a very
   large TV library.)
3. **Languages**: *Which language do you speak?* (taken from your browser)
   and *Also keep each title's original language* (recommended). See
   [Languages](languages.md).
4. **Size and quality**: three cards, **Smallest**, **Balanced**
   (recommended) and **Best quality**, each showing roughly how much space it
   would save on *this* library. A fourth card, **Copy a file I like**, lets
   you pick a file from this library whose size and picture you like:
   ReelHaven reads how it was made, shows what it found and what it would
   save, and **Choose this** makes it the choice (click the card again to pick
   another file). On **Next** it is saved as a profile named *Like <file
   name>* (see [Mimic a file](mimic.md)). While the library is still being read, the
   estimates appear after the first 200 files and are worked out from the
   files read so far (the step says how many); they get more accurate as
   reading continues. **More options** lets you pick another
   profile you made, or *Don't re-encode video* to only change languages.
5. **Audio**: **Keep audio as it is** (recommended), **Shrink big audio
   tracks, keep surround**, or **Stereo only (smallest)**, each with the extra
   space it saves. Stereo removes surround sound for good once the originals
   leave the [recycle bin](recycle-bin.md). (Skipped if the video isn't
   re-encoded.) If the size-and-quality profile you picked has its own
   audio setup (for example one made with [Mimic a file](mimic.md)), a fourth
   choice, **As set in this profile**, comes first and is preselected. Shrink
   and Stereo then keep that profile's audio format and bitrate. When the
   choice converts audio, the step says what its bitrate sounds like, with
   the chart and Plex note from
   [What the bitrates mean](profiles.md#what-the-bitrates-mean).
6. **Try it**: ReelHaven tries your choice on 2 files, one after the other, so
   you can look at the first result while the second is encoding. Your
   originals aren't touched. Compare the pictures (**Look closer, full
   screen** zooms in on five moments and plays the same scene from both; see
   [Compare full screen](test-run.md#compare-full-screen)): if you can't tell
   them apart, click **Looks good**. Otherwise **Try another setting** takes you
   back to step 4. This is the [test run](test-run.md) that unlocks
   re-encoding the library.
7. **Safety net**: how long replaced originals stay in the
   [recycle bin](recycle-bin.md): Off, 1, 3, 7, **14** (recommended) or 30
   days. This applies to every library. Choosing **Off** means files can't be
   put back, so the wizard asks you to tick *I understand* first.
8. **Go automatic**: **Yes, automatically** (recommended) works through every
   file, a few at a time, and handles new files as they arrive. **Not yet,
   just watch** finds and plans new files but changes nothing. See
   [Automatic processing](automation.md).
   If the library is still being read, nothing changes until ReelHaven has
   finished reading it and looked up each title's original language; your
   choice applies from then on.

The last screen links to the **Jobs** page to watch the progress, or lets you
set up another library.

## Good to know

- You can go **Back** at any step. Leaving and coming back returns to the
  same step.
- If the test run waits for "a free encoder" forever, no graphics card is set
  up for the chosen format and CPU encoding is off; the step says what to do.
  See [Hardware](hardware.md).
- Nothing the wizard does is special: everything it sets can be changed later
  on the library, profile and hardware pages.
