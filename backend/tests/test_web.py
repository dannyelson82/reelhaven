from pathlib import Path

from fastapi.testclient import TestClient

from reelhaven.app import create_app


def test_serves_built_frontend(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>ReelHaven</title>")
    client = TestClient(create_app(web_dir=tmp_path))
    response = client.get("/")
    assert response.status_code == 200
    assert "ReelHaven" in response.text


def test_api_routes_win_over_static_files(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("index")
    client = TestClient(create_app(web_dir=tmp_path))
    assert client.get("/healthz").json() == {"status": "ok"}


def test_without_frontend_only_api_is_served(tmp_path: Path) -> None:
    client = TestClient(create_app(web_dir=tmp_path))
    assert client.get("/").status_code == 404
    assert client.get("/healthz").status_code == 200


def test_static_files_cannot_escape_web_dir(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("index")
    (tmp_path / "secret.txt").write_text("do not serve")
    client = TestClient(create_app(web_dir=web))
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt"):
        response = client.get(path)
        assert "do not serve" not in response.text
