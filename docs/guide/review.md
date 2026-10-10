---
title: Review
order: 95
summary: One page for every file that needs your decision, from wrong-language releases to failed jobs.
---

# Review

**Review** (in the menu) lists every file that needs a decision, from all
libraries. The number next to it counts what's left to look at. Nothing on
this page changes files by itself.

## Tabs

| Tab | What it means |
|---|---|
| **Wrong language** | None of the audio is in the library's languages, for example an English film with only Spanish audio: probably the wrong release. It shows the audio languages and the title's original language. Untagged audio never counts as wrong. |
| **Failed** | The file's last job failed. The original wasn't changed. **Try again** queues it again. |
| **Can't be read** | ReelHaven couldn't read the file. It may be damaged, or still being copied; it's read again when it changes. |
| **Not re-encoded** | Dolby Vision and HDR10+ files, which ReelHaven never re-encodes (it would lose their extra picture information). Their languages are still handled. |
| **No gain** | Re-encoding, or converting the audio, didn't make the file smaller, so the original was kept. It isn't tried again with the same settings. |
| **Waiting** | The title's original language hasn't been looked up yet, so the file waits (see [Languages](languages.md)). Not counted in the menu: it sorts itself out. |

## Actions

- **Quarantine** and **Delete** (wrong-language files, after you confirm) move
  the file out of the library and ask Sonarr/Radarr for another release (see
  [Languages](languages.md#wrong-language-files)).
- **Open library** goes to the file's library.
- **Ignore** hides the file from that tab and from the count. If the file
  changes (a new release, for example), it shows up again.
  **Show ignored** lists ignored files, with **Show again**.

The page updates every minute.
