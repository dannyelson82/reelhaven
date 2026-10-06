"""HTTP clients for the services ReelHaven talks to.

Outbound requests go only to the configured URL (no redirects followed),
with TLS verification on by default and short timeouts (SECURITY.md).
"""

import re
from typing import Any, Literal, Self
from urllib.parse import urlsplit

import httpx

from reelhaven import __version__

TMDB_URL = "https://api.themoviedb.org"
TIMEOUT_S = 10.0
_USER_AGENT = f"ReelHaven/{__version__}"

ErrorCode = Literal[
    "invalid_url",
    "unreachable",
    "timeout",
    "tls_error",
    "unauthorized",
    "wrong_app",
    "redirected",
    "bad_response",
]


class IntegrationError(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def validate_base_url(url: str) -> str:
    """Normalise a service URL; refuses credentials, queries and odd schemes."""
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise IntegrationError("invalid_url", "Use a full address like http://192.168.1.10:8989")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise IntegrationError("invalid_url", "The address can't contain a login, ? or #")
    return url.rstrip("/")


class ServiceClient:
    def __init__(
        self,
        base_url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        verify_tls: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = validate_base_url(base_url)
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json", **(headers or {})},
            params=params,
            verify=verify_tls,
            timeout=TIMEOUT_S,
            follow_redirects=False,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def test(self) -> dict[str, str]:
        raise NotImplementedError

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            response = self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise IntegrationError("timeout", "The service didn't answer in time") from exc
        except httpx.ConnectError as exc:
            if "CERTIFICATE" in str(exc).upper() or "SSL" in str(exc).upper():
                raise IntegrationError(
                    "tls_error",
                    "The HTTPS certificate isn't trusted. For a self-signed certificate, "
                    "turn off certificate checking.",
                ) from exc
            raise IntegrationError("unreachable", "Couldn't connect to that address") from exc
        except httpx.HTTPError as exc:
            raise IntegrationError("unreachable", "Couldn't connect to that address") from exc
        if response.status_code in (401, 403):
            raise IntegrationError("unauthorized", "The API key was rejected")
        if response.is_redirect:
            raise IntegrationError(
                "redirected",
                "The service redirected elsewhere; check the address (http vs https, URL base)",
            )
        if response.status_code >= 400:
            raise IntegrationError(
                "bad_response", f"The service answered HTTP {response.status_code}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise IntegrationError(
                "bad_response", "The answer wasn't JSON. Is this the right address?"
            ) from exc


class ArrClient(ServiceClient):
    """Sonarr or Radarr (API v3)."""

    def __init__(
        self,
        kind: Literal["sonarr", "radarr"],
        base_url: str,
        api_key: str,
        *,
        verify_tls: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(
            base_url, headers={"X-Api-Key": api_key}, verify_tls=verify_tls, transport=transport
        )
        self.kind = kind

    def test(self) -> dict[str, str]:
        status = self.get_json("/api/v3/system/status")
        app = str(status.get("appName", "")) if isinstance(status, dict) else ""
        if app.lower() != self.kind:
            raise IntegrationError(
                "wrong_app", f"That address is {app or 'not'} a {self.kind.title()} server"
            )
        return {"app": app, "version": str(status.get("version", ""))}


_TMDB_V3_KEY = re.compile(r"^[0-9a-f]{32}$")


class TmdbClient(ServiceClient):
    """TMDB API v3, with either a v3 API key or a v4 read access token."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = TMDB_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        key = api_key.strip()
        if _TMDB_V3_KEY.match(key):
            super().__init__(base_url, params={"api_key": key}, transport=transport)
        else:
            super().__init__(
                base_url, headers={"Authorization": f"Bearer {key}"}, transport=transport
            )

    def test(self) -> dict[str, str]:
        self.get_json("/3/configuration")
        return {"app": "TMDB", "version": "3"}
