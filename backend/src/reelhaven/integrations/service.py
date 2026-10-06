"""Build clients from stored integrations (decrypting their keys)."""

from typing import Any

import httpx

from reelhaven.db import Integration
from reelhaven.integrations.clients import TMDB_URL, ArrClient, TmdbClient
from reelhaven.secretbox import SecretBox


def make_client(
    kind: str,
    base_url: str,
    api_key: str,
    verify_tls: bool,
    transport: httpx.BaseTransport | None = None,
) -> ArrClient | TmdbClient:
    if kind in ("sonarr", "radarr"):
        return ArrClient(kind, base_url, api_key, verify_tls=verify_tls, transport=transport)  # type: ignore[arg-type]
    if kind == "tmdb":
        return TmdbClient(api_key, base_url=base_url or TMDB_URL, transport=transport)
    raise ValueError(f"unknown integration kind: {kind}")


def client_for(
    integration: Integration, box: SecretBox, transport: httpx.BaseTransport | None = None
) -> ArrClient | TmdbClient:
    return make_client(
        integration.kind,
        integration.base_url,
        box.decrypt(integration.api_key_encrypted),
        integration.verify_tls,
        transport,
    )


def key_hint(box: SecretBox, integration: Integration) -> str:
    """Last four characters only: enough to recognise, useless to an attacker."""
    try:
        return "…" + box.decrypt(integration.api_key_encrypted)[-4:]
    except Exception:  # undecryptable key: shown as missing so the user re-enters it
        return ""


def as_dict(integration: Integration, box: SecretBox) -> dict[str, Any]:
    return {
        "id": integration.id,
        "kind": integration.kind,
        "name": integration.name,
        "base_url": integration.base_url,
        "verify_tls": integration.verify_tls,
        "path_mappings": integration.path_mappings,
        "enabled": integration.enabled,
        "api_key_hint": key_hint(box, integration),
    }
