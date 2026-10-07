---
title: Getting started
order: 10
summary: Install ReelHaven on Unraid, create your account and process your first library safely.
---

# Getting started

ReelHaven makes your video library smaller and tidier. It re-encodes video into
a more efficient format and removes audio and subtitle tracks in languages you
don't want. It never changes a file until you ask it to. Every new file is
checked before it replaces the original, and originals are kept in a
[recycle bin](recycle-bin.md) for 14 days.

## Install on Unraid

Install ReelHaven from the template. The important settings:

| Setting | Container path | What it's for |
|---|---|---|
| **Config** | `/config` | Database, settings, logs and keys. Keep it in appdata. |
| **Media** | `/media` | Your media share. Libraries are folders under `/media`. |
| **Transcode** | `/transcode` | Temporary encode output. A fast disk (cache pool) is best. |
| **Web UI Port** | `7171` | The address you open in the browser. |

To let ReelHaven use your graphics card(s), see [Hardware](hardware.md).

## First start

1. Open the web UI (`http://<your-server>:7171`).
2. Create the admin account. The password needs at least 10 characters; a
   short sentence works well.
3. Do this before exposing ReelHaven to the internet.

## The safe way to start

1. **Add a library** on the [Libraries](libraries.md) page (for example your
   Movies folder) and click **Scan library**.
2. Optionally connect **Sonarr**, **Radarr** or **TMDB** on the
   [Integrations](integrations.md) page, so ReelHaven knows each title's
   original language.
3. Check the library's **[Language policy](languages.md)**.
4. Choose a **[compression profile](profiles.md)** for the library, or leave
   it on *No encoding* to only change languages.
5. Run a **[Dry run](dry-run.md)**. It shows what would happen and changes
   nothing.
6. If the library will be re-encoded, do a **[Test run](test-run.md)** and
   approve it.
7. **Apply** the dry run and follow progress on the [Jobs](jobs.md) page.

## Coming later

Automatic processing of new files (folder watching, Sonarr/Radarr webhooks)
and the statistics dashboard arrive in later versions. For now, processing is
always started by you.
