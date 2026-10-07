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
