# 0028: How long originals are kept, including not at all

- Status: accepted
- Date: 2026-10-08

## Context
Every replaced original goes to a recycle bin in the library's `.reelhaven`
folder and stays for a fixed 14 days (ARCHITECTURE.md §6.8 calls it
configurable, but it never was). On a large library that holds back a lot of
space for two weeks after compressing it. The owner wants the recycle bin to be
optional. SECURITY.md (*Data safety*) says originals go to a recycle bin, so
this is recorded here.

## Decision
- One **server-wide** setting, *Keep originals for*: **Off**, 1, 3, 7, **14**
  (default) or 30 days. It is shown on the Recycle bin page and asked in the
  setup wizard (*Safety net* step, before *Go automatic*).
- **Off** deletes an original as soon as its replacement has passed
  verification. The replacer is unchanged: the original is still moved into
  the bin and the output renamed into place; the recycle item is then deleted
  straight away and marked purged (audit: `recycle.skipped`). The item is
  saved as already expired, so if that delete fails or ReelHaven stops first,
  the regular purge removes it.
- A restore's displaced file (*restore-swap*) follows the same setting.
- A change applies only to files replaced from then on; items already in the
  bin keep their expiry date (they can be deleted by hand).
- Shortening the time or turning the bin off asks for confirmation (a dialog on
  the Recycle bin page, an *I understand* tick in the wizard) and every change
  is written to the audit log (`recycle.settings_changed`).
- Verification, the test-run gate and review flags are unchanged: with the bin
  off they are the only safety net.

## Consequences
- With the bin off, a bad result can't be undone; the UI says so wherever it
  mentions the recycle bin, including the stereo downmix warning.
- Space-saved statistics are unaffected (they count replacements; restores
  only exist while an item is in the bin).
