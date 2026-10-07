---
title: Security and access
order: 110
summary: Your account, local-network access, reverse proxies and the API key.
---

# Security and access

ReelHaven can delete and replace files, so it always needs a login unless you
choose otherwise. All settings are on the **Security** page.

## Your account

- The admin account is created on first start (password at least 10
  characters).
- **Change password**: logs out every other device.
- **Log out** and **Log out everywhere** are in the menu under your name.
- After 3 wrong passwords, each further attempt has to wait a little longer
  (up to 15 minutes).
- **Log out after this many days of inactivity**: default 7 days.

## Skipping the login on your home network

**Don't require login on my local network** (off by default) lets devices on
private addresses (192.168.x.x, 10.x.x.x, …) use ReelHaven without logging
in. The page shows **Your address as ReelHaven sees it**, and whether it
counts as local.

- If you reach ReelHaven from the internet through a **reverse proxy** on
  your network, add the proxy's address under **Trusted reverse proxies**.
  Otherwise everyone coming through the proxy would look local and skip the
  login.
- Requests that arrive from Docker's own network gateway can't be traced to a
  device, so they always have to log in. The page warns you when that
  happens.
- Without a login, pages update every few seconds instead of live.

## Trusted reverse proxies

One IP address or range per line, e.g. `192.168.1.50`. Only these may tell
ReelHaven the real address of the visitor. Leave it empty if you don't use a
reverse proxy.

## API key

For scripts (and, in a later version, Sonarr/Radarr webhooks). It can't change
security settings.

- **Create API key** shows the key **once**. Copy it then; it isn't shown
  again.
- **Replace API key** makes the old key stop working immediately.
