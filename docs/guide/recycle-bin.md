---
title: Recycle bin
order: 100
summary: Replaced originals are kept for a while (14 days unless you change it) and can be restored.
---

# Recycle bin

Every file ReelHaven replaces is kept in the **recycle bin**, for **14 days**
unless you choose otherwise (below).
It's stored on the same disk as your library, in a hidden `.reelhaven` folder
at the library's root, so nothing is copied between disks.

On the **Recycle bin** page:

- **Restore** puts the original back exactly as it was. The version it
  replaces goes into the recycle bin in turn, so a restore can be undone too.
- **Delete** removes an item for good, after you confirm. This can't be
  undone.
- Items are deleted automatically when their time is up. Each card shows the
  date.
- **Show restored and deleted items** includes the history.
- The page shows how much space the recycle bin uses.
- The **Quarantine** tab lists wrong-language files moved out of your
  libraries while Sonarr/Radarr look for another release (see
  [Languages](languages.md#wrong-language-files)). They're kept, restored and
  deleted the same way.

## How long originals are kept

At the top of the page, **Keep originals for** sets how long replaced files
stay in the bin: **Off**, 1, 3, 7, **14** (recommended) or 30 days. The same
choice is offered in the [setup wizard](setup-wizard.md) (*Safety net*). It
applies to every library.

- The space an original takes comes back only when it leaves the bin, so a
  shorter time frees space sooner. A longer time gives you more chance to
  notice a problem.
- **Off** means no recycle bin: an original is deleted as soon as its new
  version has passed every check (it plays to the end and has the right
  tracks and length). You get the space back straight away, but **nothing can
  be restored**. Surround sound removed by a stereo downmix is gone for good.
- Making the time shorter, or turning the bin off, asks you to confirm and is
  written to the audit log.
- A change only affects files replaced from then on. Originals already in the
  bin keep their date; delete them here if you need the space now.
