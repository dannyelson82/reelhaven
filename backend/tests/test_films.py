"""Test films (ADR-0031): downloads on request, checked, kept in appdata; sessions on them."""

import hashlib
import io
import os
import threading
import zipfile
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from reelhaven import films
from reelhaven.config import Settings
from reelhaven.films import CATALOGUE, Film, FilmLibrary
from tests.helpers import API, admin_client
from tests.media_fixtures import FFMPEG, Spec, make
from tests.test_encode_pipeline import FAST, app  # noqa: F401 - shared fixture

pytestmark = pytest.mark.skipif(
    FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed"
)

BASE = CATALOGUE[0]


def _zip(name: str, data: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr("README.txt", b"not this one")
        zipped.writestr(name, data)
    return buffer.getvalue()


def _film(body: bytes, member: str | None = "film.mp4", **extra: object) -> Film:
    fields: dict[str, object] = {
        "id": "test-film",
        "url": "https://films.example/test.zip",
        "download_bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "member": member,
        **extra,
    }
    return replace(BASE, **fields)  # type: ignore[arg-type]


def _serve(
    body: bytes, status: int = 200, gate: threading.Event | None = None
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        def chunks() -> Iterator[bytes]:
            for start in range(0, len(body), 1000):
                if gate is not None:
                    gate.wait(5)
                yield body[start : start + 1000]

        return httpx.Response(status, content=chunks())

    return httpx.MockTransport(handler)


def test_catalogue_is_https_and_checked() -> None:
    assert len({f.id for f in CATALOGUE}) == len(CATALOGUE)
    for item in CATALOGUE:
        assert item.url.startswith("https://") and len(item.sha256) == 64
        assert item.licence.startswith("CC BY") and item.licence_url.startswith("https://")


def test_download_checks_and_unpacks(tmp_path: Path) -> None:
    body = _zip("film.mp4", b"x" * 5000)
    item = _film(body)
    library = FilmLibrary(tmp_path, _serve(body))
    assert library.state(item)[0] == "available"
    library.download(item)
    assert library.wait(item, 10) == "ready"
    assert library.path(item).read_bytes() == b"x" * 5000  # only the film, not the README
    assert sorted(p.name for p in (tmp_path / item.id).iterdir()) == ["film.mp4"]
    library.delete(item)
    assert library.state(item)[0] == "available" and not (tmp_path / item.id).exists()


def test_damaged_download_is_thrown_away(tmp_path: Path) -> None:
    body = _zip("film.mp4", b"x" * 5000)
    item = replace(_film(body), sha256="0" * 64)
    library = FilmLibrary(tmp_path, _serve(body))
    library.download(item)
    assert library.wait(item, 10) == "failed"
    assert "checksum" in (library.state(item)[2] or "")
    assert not (tmp_path / item.id).exists()


def test_cancelling_a_download(tmp_path: Path) -> None:
    body = b"y" * 50_000
    item = _film(body, member=None, url="https://films.example/film.mkv")
    gate = threading.Event()
    library = FilmLibrary(tmp_path, _serve(body, gate=gate))
    library.download(item)
    assert library.state(item)[0] == "downloading"
    library.delete(item)
    gate.set()
    library.wait(item, 10)
    assert library.state(item)[0] == "available" and not (tmp_path / item.id).exists()


def test_films_api_and_a_session_on_a_film(
    app: FastAPI,  # noqa: F811
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = admin_client(app)
    admin.put(
        f"{API}/devices/settings", json={"cpu_enabled": True, "cpu_concurrency": 1, "devices": {}}
    )
    listed = admin.get(f"{API}/films").json()
    assert [f["id"] for f in listed] == [f.id for f in CATALOGUE]
    assert {f["state"] for f in listed} == {"available"}  # nothing downloads by itself

    # A film already downloaded: sessions can use it, with no library.
    item = replace(_film(b""), member=None, url="https://films.example/film.mkv")
    monkeypatch.setattr(films, "CATALOGUE", (item,))
    path = app.state.films.path(item)
    path.parent.mkdir(parents=True)
    make(path.with_suffix(".tmp.mkv"), Spec(size="1280x720", seconds=3, video_bitrate="12M"))
    path.with_suffix(".tmp.mkv").rename(path)
    assert admin.get(f"{API}/films").json()[0]["state"] == "ready"

    started = admin.post(f"{API}/tune-sessions", json={"film_id": item.id, "settings": FAST})
    assert started.status_code == 201, started.text
    tune = started.json()
    assert (tune["film_id"], tune["library_id"], tune["file"]) == (item.id, None, item.title)
    assert app.state.queue.wait_idle(300)
    added = admin.post(f"{API}/tune-sessions/{tune['id']}/steps", json={"quality": 5})
    assert added.status_code == 201, added.text
    assert app.state.queue.wait_idle(300)
    steps = admin.get(f"{API}/tune-sessions/{tune['id']}").json()["steps"]
    assert {s["status"] for s in steps} == {"done"}, steps
    jobs = admin.get(f"{API}/jobs").json()["items"]
    assert {(j["type"], j["library_id"]) for j in jobs} == {("tune", None)}

    both = admin.post(
        f"{API}/tune-sessions", json={"film_id": item.id, "file_id": 1, "settings": FAST}
    )
    assert both.status_code == 422
    unknown = admin.post(f"{API}/tune-sessions", json={"film_id": "nope", "settings": FAST})
    assert unknown.status_code == 404
    assert admin.post(f"{API}/films/nope/download").status_code == 404

    # Deleting the film: later steps can't be added.
    assert admin.delete(f"{API}/films/{item.id}").json()["state"] == "available"
    gone = admin.post(f"{API}/tune-sessions/{tune['id']}/steps", json={"quality": 3})
    assert gone.status_code == 409 and gone.json()["detail"] == "film_gone"
