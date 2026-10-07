---
title: Integrations
order: 40
summary: Connect Sonarr, Radarr and TMDB so ReelHaven knows each title's original language.
---

# Integrations

ReelHaven asks these services what language each title was originally made
in (see [Languages](languages.md)). Add them on the **Integrations** page.

| Service | Gives | Where to find the API key |
|---|---|---|
| **Sonarr** | Original language of each series | Sonarr → Settings → General → Security |
| **Radarr** | Original language of each movie | Radarr → Settings → General → Security |
| **TMDB** | Fallback for titles Sonarr/Radarr don't manage | Free key: themoviedb.org → Settings → API |

## Add Sonarr or Radarr

1. Click **Add Sonarr** (or **Add Radarr**).
2. **Address**: the full address, e.g. `http://192.168.1.10:8989`. Include
   the URL base if you set one, e.g. `http://host:8989/sonarr`.
3. **API key**: paste it.
4. **Check the HTTPS certificate**: leave on. Turn off only for a
   self-signed certificate on your own network.
5. **Path mappings**: only needed if Sonarr/Radarr sees your files at a
   different path, e.g. Sonarr uses `/tv` where ReelHaven uses `/media/TV`.
   Add one line: `/tv` → `/media/TV`.
6. Click **Test connection**, then **Save**.

Then open each library and click **Refresh languages**.

## Good to know

- API keys are stored encrypted and never shown again after saving. To keep
  the saved key while editing, leave the field empty.
- Switch an integration **Enabled** off to pause it without deleting it.

## Webhooks: hear about new files straight away

Sonarr and Radarr can tell ReelHaven the moment they import, upgrade, rename
or delete a file. Libraries set to **Watch** or **Automatic** (see
[Automatic processing](automation.md)) are then rescanned within a minute.
The **Webhooks** card at the bottom of the Integrations page shows the exact
address to use and the last notification each app sent.

1. Create an API key on the [Security](security.md) page if you don't have
   one (**Create API key**). Copy it: it's shown only once.
2. In Sonarr (or Radarr): **Settings → Connect → +**, choose **Webhook**, and
   name it *ReelHaven*.
3. Tick these triggers:
   - Sonarr: **On Import**, **On Upgrade**, **On Rename**, **On Series
     Delete**, **On Episode File Delete**.
   - Radarr: **On Import**, **On Upgrade**, **On Rename**, **On Movie
     Delete**, **On Movie File Delete**.
4. **URL**: copy it from the Webhooks card and replace `YOUR_API_KEY` with your
   key, e.g. `http://192.168.1.10:7171/api/v1/webhook/sonarr?apikey=…`. Use the
   server's address and port 7171, the way Sonarr can reach ReelHaven.
   **Method**: POST.
5. Click **Test**, then **Save**. The Webhooks card should show *Test: Sonarr
   can reach ReelHaven.*

What the card can show after a real import:

| Message | Meaning |
|---|---|
| *… will be rescanned shortly.* | Working. |
| *… is set to Off, so nothing happens on its own.* | Set the library's watch mode to Watch or Automatic. |
| *The path … sent isn't in any library.* | Add a path mapping to the Sonarr/Radarr integration (see step 5 under *Add Sonarr or Radarr*). |

If you replace the API key, update the URL in Sonarr and Radarr too.
