import json
import logging
import stat
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from reelhaven.app import create_app
from reelhaven.config import Settings
from reelhaven.db import AuditLog, Database
from reelhaven.integrations.clients import (
    ArrClient,
    IntegrationError,
    TmdbClient,
    validate_base_url,
)
from reelhaven.integrations.pathmap import to_local, to_remote
from reelhaven.logsetup import JsonFormatter, SecretRegistry
from reelhaven.secretbox import SecretBox, SecretBoxError
from tests.helpers import API, admin_client

SONARR_KEY = "0123456789abcdef0123456789abcdef"


# --- SecretBox ----------------------------------------------------------------------


def test_secretbox_creates_private_key_and_round_trips(tmp_path: Path) -> None:
    box = SecretBox(tmp_path)
    assert stat.S_IMODE(box.path.stat().st_mode) == 0o600
    token = box.encrypt("hunter2-api-key")
    assert "hunter2" not in token
    assert SecretBox(tmp_path).decrypt(token) == "hunter2-api-key"  # same key file reused
    assert "hunter2-api-key" in SecretRegistry.values()  # redacted from logs


def test_secretbox_fixes_loose_permissions(tmp_path: Path) -> None:
    SecretBox(tmp_path).path.chmod(0o644)
    box = SecretBox(tmp_path)
    assert stat.S_IMODE(box.path.stat().st_mode) == 0o600


def test_secretbox_wrong_key(tmp_path: Path) -> None:
    token = SecretBox(tmp_path / "a").encrypt("secret-value")
    with pytest.raises(SecretBoxError):
        SecretBox(tmp_path / "b").decrypt(token)


# --- path mapping ---------------------------------------------------------------------

MAPPINGS = [
    {"remote": "/tv", "local": "/media/TV"},
    {"remote": "/tv/anime", "local": "/media/Anime"},
    {"remote": "D:\\Movies", "local": "/media/Movies"},
]


@pytest.mark.parametrize(
    ("remote", "local"),
    [
        ("/tv/Show/S01E01.mkv", "/media/TV/Show/S01E01.mkv"),
        ("/tv/anime/One Piece/e1.mkv", "/media/Anime/One Piece/e1.mkv"),  # longest prefix
        ("/tv", "/media/TV"),
        ("/tvshows/x.mkv", "/tvshows/x.mkv"),  # not a path-component match
        ("D:\\Movies\\Film\\f.mkv", "/media/Movies/Film/f.mkv"),
        ("/other/x.mkv", "/other/x.mkv"),
    ],
)
def test_to_local(remote: str, local: str) -> None:
    assert to_local(remote, MAPPINGS) == local


def test_to_remote() -> None:
    assert to_remote("/media/TV/Show/e.mkv", MAPPINGS) == "/tv/Show/e.mkv"
    assert to_remote("/media/Anime/x.mkv", MAPPINGS) == "/tv/anime/x.mkv"


# --- clients ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    ["sonarr:8989", "ftp://host", "http://user:pw@host", "http://host/?x=1", "http://host/#a", ""],
)
def test_invalid_urls(url: str) -> None:
    with pytest.raises(IntegrationError) as info:
        validate_base_url(url)
    assert info.value.code == "invalid_url"


def test_url_normalised() -> None:
    assert validate_base_url(" http://10.0.0.5:8989/sonarr/ ") == "http://10.0.0.5:8989/sonarr"


Handler = Callable[[httpx.Request], httpx.Response]


def fake_arr(app_name: str = "Sonarr", key: str = SONARR_KEY) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("X-Api-Key") != key:
            return httpx.Response(401)
        if request.url.path.endswith("/api/v3/system/status"):
            return httpx.Response(200, json={"appName": app_name, "version": "4.0.9"})
        return httpx.Response(404)

    return handler


def arr(handler: Handler, kind: str = "sonarr", key: str = SONARR_KEY) -> ArrClient:
    return ArrClient(kind, "http://sonarr:8989", key, transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def test_arr_ok() -> None:
    assert arr(fake_arr()).test() == {"app": "Sonarr", "version": "4.0.9"}


def error_code(client: ArrClient | TmdbClient) -> str:
    with pytest.raises(IntegrationError) as info:
        client.test()
    return info.value.code


def test_arr_errors() -> None:
    assert error_code(arr(fake_arr(), key="wrong")) == "unauthorized"
    assert error_code(arr(fake_arr("Radarr"))) == "wrong_app"
    assert (
        error_code(arr(lambda r: httpx.Response(301, headers={"Location": "https://x"})))
        == "redirected"
    )
    assert error_code(arr(lambda r: httpx.Response(200, text="<html>"))) == "bad_response"
    assert error_code(arr(lambda r: httpx.Response(500))) == "bad_response"

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    def bad_cert(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED]", request=request)

    assert error_code(arr(timeout)) == "timeout"
    assert error_code(arr(refused)) == "unreachable"
    assert error_code(arr(bad_cert)) == "tls_error"


def test_tmdb_key_styles() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"images": {}})

    TmdbClient("a" * 32, transport=httpx.MockTransport(handler)).test()
    TmdbClient("eyJhbGciOiJIUzI1NiJ9.x.y", transport=httpx.MockTransport(handler)).test()
    assert seen[0].url.params["api_key"] == "a" * 32
    assert "authorization" not in seen[0].headers
    assert seen[1].headers["authorization"] == "Bearer eyJhbGciOiJIUzI1NiJ9.x.y"
    assert "api_key" not in seen[1].url.params
    assert seen[0].url.host == "api.themoviedb.org"


# --- API ------------------------------------------------------------------------------


@pytest.fixture
def app(settings: Settings) -> Iterator[FastAPI]:
    application = create_app(settings, gateways=frozenset(), detect_devices=False)
    application.state.http_transport = httpx.MockTransport(fake_arr())
    with TestClient(application):
        yield application


def sonarr_body(**overrides: Any) -> dict[str, Any]:
    return {
        "kind": "sonarr",
        "name": "Sonarr",
        "base_url": "http://sonarr:8989",
        "api_key": SONARR_KEY,
        "path_mappings": [{"remote": "/tv", "local": "/media/TV"}],
        **overrides,
    }


def test_crud_never_returns_the_key(app: FastAPI, caplog: pytest.LogCaptureFixture) -> None:
    admin = admin_client(app)
    with caplog.at_level(logging.DEBUG):
        created = admin.post(f"{API}/integrations", json=sonarr_body())
    assert created.status_code == 201, created.text
    body = created.json()
    assert SONARR_KEY not in created.text
    assert body["api_key_hint"] == "…" + SONARR_KEY[-4:]
    assert body["path_mappings"] == [{"remote": "/tv", "local": "/media/TV"}]

    listed = admin.get(f"{API}/integrations")
    assert SONARR_KEY not in listed.text

    # Stored encrypted, never in plaintext anywhere in the database.
    db: Database = app.state.db
    with db.read() as session:
        dump = json.dumps([list(r) for r in session.execute(text("SELECT * FROM integrations"))])
        assert SONARR_KEY not in dump
        audit_dump = json.dumps(
            [(a.action, a.detail) for a in session.scalars(select(AuditLog))], default=str
        )
        assert SONARR_KEY not in audit_dump
    assert all(SONARR_KEY not in JsonFormatter().format(r) for r in caplog.records)

    # Updating without api_key keeps the stored key.
    renamed = admin.patch(f"{API}/integrations/{body['id']}", json={"name": "Sonarr 4K"})
    assert renamed.json()["api_key_hint"] == body["api_key_hint"]
    new_key = "f" * 32
    rekeyed = admin.patch(f"{API}/integrations/{body['id']}", json={"api_key": new_key})
    assert rekeyed.json()["api_key_hint"] == "…ffff"

    assert admin.delete(f"{API}/integrations/{body['id']}").status_code == 204
    assert admin.get(f"{API}/integrations").json() == []


def test_tmdb_url_is_fixed(app: FastAPI) -> None:
    admin = admin_client(app)
    body = {"kind": "tmdb", "name": "TMDB", "base_url": "http://evil.example", "api_key": "a" * 32}
    created = admin.post(f"{API}/integrations", json=body).json()
    assert created["base_url"] == "https://api.themoviedb.org"


@pytest.mark.parametrize(
    "overrides",
    [
        {"base_url": "not a url"},
        {"kind": "plex"},
        {"api_key": ""},
        {"path_mappings": [{"remote": "tv", "local": "/media"}]},
        {"secret": "x"},
    ],
)
def test_validation(app: FastAPI, overrides: dict[str, Any]) -> None:
    admin = admin_client(app)
    assert admin.post(f"{API}/integrations", json=sonarr_body(**overrides)).status_code == 422


def test_duplicate_name(app: FastAPI) -> None:
    admin = admin_client(app)
    admin.post(f"{API}/integrations", json=sonarr_body())
    assert admin.post(f"{API}/integrations", json=sonarr_body()).status_code == 409


def test_connection_test_endpoint(app: FastAPI) -> None:
    admin = admin_client(app)
    form = {"kind": "sonarr", "base_url": "http://sonarr:8989", "api_key": SONARR_KEY}
    assert admin.post(f"{API}/integrations/test", json=form).json() == {
        "ok": True,
        "app": "Sonarr",
        "version": "4.0.9",
        "error_code": None,
        "message": None,
    }
    wrong = admin.post(f"{API}/integrations/test", json={**form, "api_key": "nope"}).json()
    assert (wrong["ok"], wrong["error_code"]) == (False, "unauthorized")
    radarr = admin.post(f"{API}/integrations/test", json={**form, "kind": "radarr"}).json()
    assert radarr["error_code"] == "wrong_app"

    # Saved integration: test without re-typing the key.
    saved = admin.post(f"{API}/integrations", json=sonarr_body()).json()
    stored = {"kind": "sonarr", "base_url": "http://sonarr:8989", "id": saved["id"]}
    assert admin.post(f"{API}/integrations/test", json=stored).json()["ok"] is True
    missing = admin.post(
        f"{API}/integrations/test", json={"kind": "sonarr", "base_url": "http://x"}
    )
    assert missing.json()["error_code"] == "missing_key"


def test_api_key_principal_cannot_manage_integrations(app: FastAPI) -> None:
    admin = admin_client(app)
    key = admin.post(f"{API}/settings/security/api-key").json()["api_key"]
    script = TestClient(app)
    assert script.get(f"{API}/integrations", headers={"X-Api-Key": key}).status_code == 403
    response = script.post(f"{API}/integrations", json=sonarr_body(), headers={"X-Api-Key": key})
    assert response.status_code == 403
