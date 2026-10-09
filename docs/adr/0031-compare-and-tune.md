# 0031: Compare and tune (phase 0.8)

- Status: accepted
- Date: 2026-10-09

## Context
Testing the setup wizard, the owner found the result hard to judge: the
comparison stills are small, there is no way to watch the original and the new
version, choosing a quality means jumping between the wizard and the Profiles
page (Mimic), and the audio bitrate settings are confusing. The owner asked to
make comparing and tuning the next phase.

## Decision
- Phase **0.8 becomes *Compare and tune***; *Insight and safety* moves to 0.9.
  One release at the end (0.8.0).
- **Comparison viewer**: a full-screen viewer for the test-run stills, with two
  modes: **side by side**, one zoom control between the images and click-and-drag
  panning, both images always showing the same spot at the same zoom; and
  **swipe**, one image with a draggable divider between original and new. Used in
  the wizard's *Try it* step and on the Test run tab.
- **Watching in the browser**: browsers can't play most MKV/HEVC/AV1 files, so
  each test-run sample gets two short **comparison clips** of the same scene
  (10–20 s), from the original and from the new file, both converted to
  near-lossless H.264 in MP4 (far finer than any difference being judged). HDR
  is tone-mapped for display and the viewer says so. The clips play in sync (play,
  pause and seek together), side by side or with the swipe divider. They live
  with the test run and go when it does.
- **Mimic in the wizard**: the size-and-quality step offers *Copy a file I like*:
  pick a file from the library, see what ReelHaven read from it and what it
  would save, and choose it like the three cards.
- **Find my sweet spot**: pick a high-quality file (from a library, or a
  downloaded test film), and ReelHaven encodes the same scene at three
  sizes, smaller and smaller, each with its estimated file size, quality rating,
  stills and comparison clips. The owner can choose one, or ask for a version
  between two of them, smaller or larger, and repeat; the choice is saved as a
  profile. Profile quality gets half steps so there is room to dial in.
- **Test films**: a built-in list of open-licence films (Blender open movies,
  Netflix open content: animation, live action, film grain, dark scenes, HDR),
  each with its licence and source. Nothing is downloaded until asked; downloads
  go to appdata and can be deleted. Library files come first in the picker.
- **Audio guidance**: next to the audio settings (profile editor and the wizard's
  audio step), a table per format of what each bitrate means (e.g. "transparent
  for most listeners"), and a note that Plex converts audio a player can't play,
  so E-AC-3 is the safest choice for playing everywhere without conversion.

## Consequences
- Test runs take a little longer and use more space in the transcode folder (the
  clips). Clips are made with the GPU where possible.
- Sweet-spot sessions encode only short scenes, so each step takes seconds to a
  minute rather than a whole film.

## Update (2026-10-09, test films)
Netflix Open Content's only downloadable MP4s (*Meridian*, *Cosmos Laundromat*)
turned out to be 8-bit H.264 with no HDR tagging, and its real HDR masters are
tens to hundreds of GB. The catalogue therefore holds Blender open movies only
(CC BY 3.0, checksums verified): no HDR test film. HDR is tried with the
owner's own files.
