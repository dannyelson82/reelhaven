# 0006: Authentication model

- Status: accepted
- Date: 2026-10-06

## Context
The owner runs ReelHaven on a LAN and doesn't want 2FA, but others may expose
it to the internet.

## Decision
Login required by default; optional local-address bypass (off by default,
client IP from the socket unless behind a configured trusted proxy); optional
TOTP 2FA with recovery codes (off by default, incompatible with the bypass);
separate API key for webhooks. Details in SECURITY.md.

## Consequences
- Safe default for everyone; convenient LAN use is one setting away.
- Trusted-proxy handling must be implemented carefully and tested.
