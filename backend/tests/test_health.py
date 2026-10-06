from fastapi.testclient import TestClient

from reelhaven.app import create_app


def test_healthz_returns_ok_without_details() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_docs_not_public() -> None:
    client = TestClient(create_app())
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
