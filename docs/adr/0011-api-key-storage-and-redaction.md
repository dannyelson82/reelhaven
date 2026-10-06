# 0011: API key storage and request-log redaction

- Status: accepted
- Date: 2026-10-06

## Context
SECURITY.md allows the API key in an `apikey` query parameter for tools that
can't set headers. Query strings end up in access logs, and SECURITY.md says
secrets are never logged.

## Decision
- The API key is 32 random bytes, shown in full once at creation or rotation.
  Only its **SHA-256 hash** and a short display prefix are stored. (A fast hash
  is appropriate for a high-entropy random key; Argon2id is for passwords.)
- Uvicorn's built-in access log is disabled. ReelHaven logs requests with its
  own middleware, which removes the `apikey` query parameter and never logs
  `Cookie`, `Authorization` or `X-Api-Key` headers.

## Consequences
- A lost key can't be recovered, only rotated, which is how GitHub tokens work too.
- Reverse proxies in front of ReelHaven may still log query strings; the UI
  and docs recommend the header form.
