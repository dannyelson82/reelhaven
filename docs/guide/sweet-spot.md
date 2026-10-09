---
title: Find my sweet spot
order: 67
summary: Encode one scene of a file at several sizes, compare them, and keep the smallest that still looks right.
---

# Find my sweet spot

How small can your files get before you can see the difference? It depends on
the film and on your eyes and screen. **Find my sweet spot** lets you check:
ReelHaven encodes the same 30-second scene of one of your files at three sizes,
smaller and smaller, and you compare each with the original. Your file isn't
touched.

Open it from **Profiles → Find my sweet spot**, or in the
[setup wizard](setup-wizard.md) under **More options** in the size and
quality step.

## Steps

1. **Pick a file**: **From a library**, choose the **Library** and click a
   file (**Search** finds it by name). A file you know well with dark scenes,
   faces or film grain shows differences best. Or pick **A test film** (see
   below).
2. **Start from profile**: the versions use this profile's format, 10-bit,
   resolution and audio; only the quality changes. **Balanced** is the
   default.
3. Click **Encode three versions**. ReelHaven makes quality 8
   (*High quality*), 6 (*Balanced*) and 4 (*Small*) on your graphics cards,
   a few seconds to a minute each. They show on the [Jobs](jobs.md) page too.

Each version shows:

- **≈ size**: the whole file's estimated size at this quality, and how much
  it saves. It's worked out from how much smaller the scene got, so a film
  whose other scenes are very different can end up a little bigger or
  smaller.
- The **rating** and quality measures, as in a [test run](test-run.md).
- **Compare**: the full-screen view with stills and the scene playing
  side by side or with the swipe divider (see
  [Compare full screen](test-run.md#compare-full-screen)).

## Dial in

Under **Try another version**:

- **Between 8 and 6: 7** tries the quality in between. Quality goes in half
  steps, so you can narrow it down to, say, 6.5.
- **Better** and **Smaller** try one step past the best or smallest so far.

A good way to use it: find the smallest version you can't tell from the
original, then the next smaller one where you can, and try the one in between.

## Keep it

**Keep this** saves the version as a profile (named *Sweet spot 6.5 (film)*,
which you can change). Choose it for a library on the library's page, and
check it with a [test run](test-run.md) before re-encoding the whole library.
Coming from the wizard, **Back to the wizard** returns with the new profile
chosen.

## Test films

**A test film** offers free films made to be shared, so you can try settings
without using your own files:

| Film | What it's good for | Download |
|---|---|---|
| **Big Buck Bunny** (1080p) | Bright animation with fur and grass; easy to compress | 276 MB |
| **Big Buck Bunny (4K)** | The same in 4K, for 4K settings and speeds | 632 MB |
| **Sintel** (1080p) | Darker animation with snow, smoke and fast action, where banding and blocks show | 1.2 GB |
| **Tears of Steel** (1080p) | Live action with effects, faces and dark scenes | 739 MB |

Each shows its licence (all Creative Commons Attribution, by the Blender
Foundation) and a link to the film's site.

- Nothing is downloaded until you click **Download**. A progress bar shows
  how far it is; **Stop** cancels it.
- Every download is checked against a known fingerprint (checksum) before
  it's kept, so a damaged or tampered file is thrown away (try again).
- Films are kept in ReelHaven's appdata folder (`films`), not in your
  libraries, so Plex never sees them. **Delete** removes one.
- When it's ready, **Use this** picks it for the session. Sessions on a test
  film show as *Test film* on the Jobs page.
- None of these films is HDR: the only free HDR test films are far too big
  (tens of GB) or not tagged as HDR. Use one of your own HDR files instead.

## Good to know

- The scene starts 40 % into the film: past the opening, well before the
  credits.
- Dolby Vision and HDR10+ files can't be used (ReelHaven never re-encodes
  them).
- ReelHaven keeps your last 3 sessions under **Recent**; older ones are
  removed with their files. **Delete** removes one now. Each session uses
  some space in the transcode folder for its scene, stills and clips.
