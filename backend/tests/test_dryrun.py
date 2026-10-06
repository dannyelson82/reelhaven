import hashlib
import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from reelhaven.app import create_app
from reelhaven.config import Settings
from reelhaven.scanner import Scanner
from tests.helpers import API, admin_client
from tests.media_fixtures import FFMPEG, Audio, Spec, Sub, make

pytestmark = pytest.mark.skipif(
    FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed"
)
OLD = time.time() - 3600


@pytest.fixture
def app(settings: Settings) -> Iterator[FastAPI]:
    application = create_app(settings, gateways=frozenset())
    application.state.scanner = Scanner(
        application.state.db,
        settings,
        stable_seconds=0,
        resolve_languages=application.state.scanner._resolve_languages,
    )
    with TestClient(application):
        yield application


def build_library(root: Path) -> None:
    files = {
        "English Film (2020)/film.mkv": Spec(audio=[Audio("eng", default=True)], subs=[Sub("eng")]),
        "Multi (2019)/multi.mkv": Spec(
            audio=[Audio("eng", default=True), Audio("fre"), Audio("ger")],
            subs=[Sub("eng", forced=True, default=True), Sub("fre")],
        ),
        "Japanese Film (2001)/jp.mkv": Spec(
            audio=[Audio("jpn", default=True)], subs=[Sub("eng"), Sub("jpn")]
        ),
        "Wrong Language (2018)/w.mkv": Spec(audio=[Audio("spa", default=True)]),
    }
    for rel, spec in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        os.utime(make(root / rel, spec), (OLD, OLD))
    (root / "Broken (2000)").mkdir()
    (root / "Broken (2000)" / "b.mkv").write_text("nope")
    os.utime(root / "Broken (2000)" / "b.mkv", (OLD, OLD))


def digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_dry_run_report(app: FastAPI, settings: Settings) -> None:
    root = settings.media_root / "Movies"
    build_library(root)
    before = digest(root)
    admin = admin_client(app)
    lib = admin.post(
        f"{API}/libraries", json={"name": "Movies", "type": "movies", "path": "Movies"}
    ).json()
    admin.post(f"{API}/libraries/{lib['id']}/scan")
    app.state.scanner.wait(lib["id"], timeout=60)

    titles = {
        t["name"]: t["id"] for t in admin.get(f"{API}/libraries/{lib['id']}/titles").json()["items"]
    }
    for name, language in [
        ("English Film", "eng"),
        ("Multi", "eng"),
        ("Japanese Film", "jpn"),
        ("Wrong Language", "eng"),
    ]:
        admin.put(f"{API}/titles/{titles[name]}/language", json={"language": language})

    report = admin.get(f"{API}/libraries/{lib['id']}/dry-run").json()
    assert report["files"] == 5
    assert report["remux"] == 2  # Multi (drop French/German), Japanese (defaults)
    assert report["unchanged"] == 2
    assert report["unreadable"] == 1
    assert report["flags"].get("wrong_language") == 1
    assert report["unknown_original"] == 1  # the broken file's title
    assert [i["relative_path"] for i in report["items"]] == [
        "Japanese Film (2001)/jp.mkv",
        "Multi (2019)/multi.mkv",
    ]
    multi = report["items"][1]
    assert "Remove audio: French, German." in multi["details"]

    flagged = admin.get(f"{API}/libraries/{lib['id']}/dry-run", params={"show": "flagged"}).json()
    assert sorted(i["relative_path"] for i in flagged["items"]) == [
        "Broken (2000)/b.mkv",
        "Wrong Language (2018)/w.mkv",
    ]
    assert (
        admin.get(f"{API}/libraries/{lib['id']}/dry-run", params={"show": "all"}).json()["total"]
        == 5
    )

    assert digest(root) == before  # a dry run never touches files


def test_dry_run_unknown_library(app: FastAPI) -> None:
    assert admin_client(app).get(f"{API}/libraries/99/dry-run").status_code == 404
