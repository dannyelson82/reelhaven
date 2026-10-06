# 0012: The local-address bypass never trusts the Docker gateway

- Status: accepted
- Date: 2026-10-06

## Context
The local-address bypass trusts the socket's client IP. In some Docker setups
(the userland proxy, IPv6-to-IPv4 forwarding, some hairpin NAT paths) every
connection arrives from the bridge gateway, e.g. `172.17.0.1`. That address is
private, so the bypass would let **everyone** in, including internet traffic.

## Decision
At startup ReelHaven reads the container's default gateway(s). Requests whose
socket address equals a gateway are **never** granted the bypass, even if that
address is listed as a trusted proxy. If such requests are seen while the bypass
is on, the security settings page shows a warning explaining why the bypass
isn't working for them.

## Consequences
- Normal Unraid bridge networking, which preserves client IPs, works as expected.
- Setups that mask client IPs get a safe failure (login required) and an explanation.
- Covered by unit tests with simulated gateway addresses.
