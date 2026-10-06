# Security

## Reporting a vulnerability

Please **do not open a public issue.** Use GitHub's private vulnerability
reporting: the "Report a vulnerability" button on this repository's
Security tab. You'll get a response as soon as practical.

## Threat model

ReelHaven is designed to run on a home server's local network. It can read,
replace, move and delete media files, so it is still treated as a sensitive
app. Some users will expose it to the internet through a reverse proxy;
the design must keep them safe when they turn on the optional protections.

What we protect against:

1. Someone on the network (or the internet, if exposed) controlling the app
   without logging in.
2. A malicious or oddly named media file causing command execution or
   writing outside the media folders.
3. Leaking API keys for Sonarr, Radarr, Plex, Jellyfin or TMDB.
4. Bugs destroying media (treated as a security concern: see "Data safety").

Out of scope: an attacker who already has root on the Unraid host.

## Authentication

- **Login required by default.** The first-run wizard creates the admin
  account. No default credentials ever ship. Until it is done, everything
  except setup and `/healthz` is blocked, and only one admin can be created
  (ADR-0013). Finish setup before exposing ReelHaven to the internet.
- Passwords hashed with **Argon2id**. Minimum length 10; no other complexity
  rules.
- **Sessions**: random 256-bit IDs, stored hashed server-side. Cookie is
  `HttpOnly`, `SameSite=Lax`, and `Secure` when the request arrived over
  HTTPS (directly or via a trusted proxy). Idle timeout 7 days (configurable);
  "log out everywhere" button.
- **Login throttling**: exponential delay per username and per IP after
  failed attempts; lockout events go to the audit log (present from phase 0.1, ADR-0010).
- **Local-address bypass** (optional, off by default, like Sonarr/Radarr's
  "Disabled for Local Addresses"): requests from private ranges
  (10/8, 172.16/12, 192.168/16, 127/8, fc00::/7, ::1) skip the login page.
  - The client IP is taken from the **socket**, never from
    `X-Forwarded-For`, unless the immediate peer is in the configured
    **trusted proxies** list. Otherwise anyone could fake a local address.
  - The UI warns that enabling this together with internet exposure through
    a reverse proxy on the same network effectively disables login.
  - Requests arriving from the container's **Docker gateway** address never
    get the bypass, because NAT can make every client look like the gateway
    (ADR-0012).
- **Two-factor (TOTP)**: optional, off by default. Any authenticator app.
  Enabling it shows 10 single-use recovery codes (stored hashed). When 2FA is
  on, the local-address bypass cannot be enabled.
- **API key**: random 32-byte key for webhooks and scripts, sent in the
  `X-Api-Key` header (or `apikey` query parameter for tools that can't set
  headers). Shown once in full, then masked; only a SHA-256 hash is stored
  (ADR-0011); rotate with one click. The API key cannot change security
  settings. The `apikey` query parameter is stripped from ReelHaven's request
  logs; prefer the header.

## Web protections

- CSRF: session-authenticated state-changing requests require a CSRF token
  (double-submit); API-key requests are exempt since they carry no cookie.
- Security headers: `Content-Security-Policy` (self only),
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`,
  `X-Frame-Options: DENY`.
- WebSocket connections require a valid session and check `Origin`.
- OpenAPI docs only for authenticated users.
- All input validated with Pydantic models; unknown fields rejected.

## File system confinement

- ReelHaven only reads and writes inside paths configured as libraries,
  `/transcode`, and `/config`. Its own `.reelhaven/` folders inside each
  library are never shown by the file browser or scanned as media.
- Every path from the UI, API or webhooks is resolved with `realpath` and
  rejected if it falls outside an allowed root. **Symlinks are resolved
  before the check**, so a link can't point the app at other host folders.
- File browser endpoints apply the same rule.
- Uploaded mimic samples: max 64 MiB, written to a temp folder with a
  random name, deleted after probing, never served back.

## Process execution

- ffmpeg and ffprobe are run with `subprocess` using an **argument list**,
  never a shell. File paths are passed as single arguments, so names with
  spaces, quotes, `;` or `$()` are harmless.
- Paths that begin with `-` are prefixed with `./` or passed after `--`
  where supported, so they can't be read as options. Input **and output**
  paths always use the `file:` protocol prefix so ffmpeg never interprets
  them as URLs or other protocols.
- Encodes run with a timeout and resource limits; a hung ffmpeg is killed.

## Secrets

- Third-party API keys and TOTP secrets are encrypted at rest with a key
  generated on first run and stored in `/config/secret.key`
  (permissions `0600`, owned by PUID).
- Secrets are never returned in full by the API (masked), never logged
  (logging filter redacts known secret values and common key patterns), and
  never included in diagnostics exports.
- Outbound requests to integrations use the configured URL only; TLS
  verification on by default (toggle for self-signed certs, with a warning).

## Container hardening

- Runs as PUID:PGID, not root, after the init step.
- No Docker socket, no privileged mode. GPU access through the NVIDIA runtime
  or `/dev/dri` only.
- Minimal base image, dependencies pinned, image scanned in CI.

## Data safety

Not strictly security, but the same mindset:

- No file is replaced until the new file passes verification
  (ARCHITECTURE.md §6.7).
- Originals go to a recycle bin; deletes go to the recycle bin too.
- New libraries require a successful test run before automatic processing.
- Destructive settings changes (enabling delete, bulk actions) require
  confirmation and are written to the audit log.

## Development practices

- Never commit secrets. GitHub secret scanning with push protection is on.
- Signed commits required on `main`.
- Dependabot alerts and security updates on.
- Personal infrastructure details (server IPs, domains, container names)
  are never committed; developer notes about a specific setup go in the
  gitignored `LOCAL_NOTES.md`.
