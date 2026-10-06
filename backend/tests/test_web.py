from pathlib import Path

from fastapi.testclient import TestClient

from reelhaven.app import create_app
from reelhaven.config import Settings


def _client(tmp_path: Path, web: Path) -> TestClient:
    return TestClient(create_app(Settings(config_dir=tmp_path / "config", web_dir=web)))


def test_serves_built_frontend(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>ReelHaven</title>")
    response = _client(tmp_path, tmp_path).get("/")
    assert response.status_code == 200
    assert "ReelHaven" in response.text


def test_api_routes_win_over_static_files(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("index")
    assert _client(tmp_path, tmp_path).get("/healthz").json() == {"status": "ok"}


def test_without_frontend_only_api_is_served(tmp_path: Path) -> None:
    client = _client(tmp_path, tmp_path / "missing")
    assert client.get("/").status_code == 404
    assert client.get("/healthz").status_code == 200


def test_static_files_cannot_escape_web_dir(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("index")
    (tmp_path / "secret.txt").write_text("do not serve")
    client = _client(tmp_path, web)
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt"):
        assert "do not serve" not in client.get(path).text
