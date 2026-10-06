import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from reelhaven.app import create_app
from reelhaven.config import Settings
from reelhaven.db import Database, Library, MediaFile
from reelhaven.scanner import Scanner, ScanProgress, is_ignored_file, walk
from tests.helpers import API, admin_client
from tests.media_fixtures import FFMPEG, Audio, Spec, Sub, make

pytestmark = pytest.mark.skipif(
    FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed"
)

OLD = time.time() - 3600  # mtime old enough to count as "finished copying"


def age(path: Path) -> Path:
    os.utime(path, (OLD, OLD))
    return path


@pytest.fixture(scope="module")
def sample(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One generated file, copied into libraries by the tests (fast)."""
    return make(
        tmp_path_factory.mktemp("src") / "sample.mkv",
        Spec(audio=[Audio("eng", default=True), Audio("fre")], subs=[Sub("eng", forced=True)]),
    )


def put(sample: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(sample.read_bytes())
    return age(dest)


@pytest.mark.parametrize(
    ("name", "ignored"),
    [
        ("Movie (2020).mkv", False),
        ("Show S01E01.mp4", False),
        ("movie.M2TS", False),
        ("notes.txt", True),
        ("poster.jpg", True),
        (".hidden.mkv", True),
        ("movie-sample.mkv", True),
        ("Sample.mkv", True),
        ("movie-trailer.mp4", True),
        ("Samples of Life (2019).mkv", False),
    ],
)
def test_is_ignored_file(name: str, ignored: bool) -> None:
    assert is_ignored_file(name) is ignored


def test_walk_skips_extras_internal_and_escaping_links(sample: Path, tmp_path: Path) -> None:
    root = tmp_path / "lib"
    put(sample, root / "A (2020)" / "A (2020).mkv")
    put(sample, root / "A (2020)" / "Featurettes" / "making of.mkv")
    put(sample, root / "B" / "Sample" / "b.mkv")
    put(sample, root / ".reelhaven" / "recycle" / "1" / "old.mkv")
    put(sample, root / ".hidden" / "x.mkv")
    outside = put(sample, tmp_path / "elsewhere" / "secret.mkv")
    (root / "link.mkv").symlink_to(outside)
    fresh = root / "C" / "copying.mkv"
    fresh.parent.mkdir()
    fresh.write_bytes(sample.read_bytes())  # mtime = now: still being written

    found, unstable = walk(root.resolve(), stable_seconds=120, now=time.time())
    assert [f.relative for f in found] == ["A (2020)/A (2020).mkv"]
    assert unstable == 1


def scanner_for(db: Database, settings: Settings) -> Scanner:
    return Scanner(db, settings, stable_seconds=0)


def run_scan(scanner: Scanner, library_id: int) -> ScanProgress:
    progress = ScanProgress(library_id)
    scanner.scan(library_id, progress)
    return progress


@pytest.fixture
def library(db: Database, settings: Settings) -> Library:
    root = settings.media_root / "Movies"
    root.mkdir()
    with db.write() as session:
        library = Library(name="Movies", type="movies", path=str(root.resolve()))
        session.add(library)
    return library


def rows(db: Database) -> list[MediaFile]:
    with db.read() as session:
        return list(session.scalars(select(MediaFile).order_by(MediaFile.relative_path)))


def test_scan_lifecycle(db: Database, settings: Settings, library: Library, sample: Path) -> None:
    root = Path(library.path)
    scanner = scanner_for(db, settings)
    put(sample, root / "One" / "one.mkv")
    put(sample, root / "Two" / "two.mkv")
    (root / "broken.mkv").write_text("not a video")
    age(root / "broken.mkv")

    first = run_scan(scanner, library.id)
    assert (first.found, first.probed, first.failed) == (3, 3, 1)
    files = {r.relative_path: r for r in rows(db)}
    assert files["broken.mkv"].status == "probe_failed"
    assert files["broken.mkv"].probe_error
    one = files["One/one.mkv"]
    assert one.status == "ok"
    assert one.probe is not None
    assert [s["language"] for s in one.probe["streams"] if s["kind"] == "audio"] == ["eng", "fra"]

    # Nothing changed: no re-probing.
    second = run_scan(scanner, library.id)
    assert (second.unchanged, second.probed) == (3, 0)

    # Moved file keeps its row (and probe) instead of being re-probed.
    (root / "Renamed").mkdir()
    (root / "Two" / "two.mkv").rename(root / "Renamed" / "two.mkv")
    # Modified file is re-probed.
    put(sample, root / "One" / "one.mkv")
    os.utime(root / "One" / "one.mkv", (OLD + 10, OLD + 10))
    # Deleted file disappears.
    (root / "broken.mkv").unlink()

    third = run_scan(scanner, library.id)
    assert (third.moved, third.probed, third.removed) == (1, 1, 1)
    after = {r.relative_path: r for r in rows(db)}
    assert set(after) == {"One/one.mkv", "Renamed/two.mkv"}
    assert after["Renamed/two.mkv"].id == files["Two/two.mkv"].id


def test_missing_library_folder_is_an_error(
    db: Database, settings: Settings, library: Library
) -> None:
    Path(library.path).rmdir()
    with pytest.raises(FileNotFoundError):
        run_scan(scanner_for(db, settings), library.id)


# --- API ---------------------------------------------------------------------------


@pytest.fixture
def app(settings: Settings) -> Iterator[FastAPI]:
    application = create_app(settings, gateways=frozenset(), detect_devices=False)
    application.state.scanner = Scanner(application.state.db, settings, stable_seconds=0)
    with TestClient(application):
        yield application


def test_scan_and_browse_files_api(app: FastAPI, settings: Settings, sample: Path) -> None:
    admin = admin_client(app)
    root = settings.media_root / "TV"
    put(sample, root / "Show" / "S01E01.mkv")
    put(sample, root / "Show" / "S01E02.mkv")
    (root / "Show" / "bad_100%.mkv").write_text("x")
    age(root / "Show" / "bad_100%.mkv")
    library = admin.post(f"{API}/libraries", json={"name": "TV", "type": "tv", "path": "TV"}).json()

    assert admin.post(f"{API}/libraries/{library['id']}/scan").json() == {"started": True}
    app.state.scanner.wait(library["id"], timeout=60)
    status = admin.get(f"{API}/libraries/{library['id']}/scan").json()
    assert (status["state"], status["found"], status["failed"]) == ("done", 3, 1)

    listed = admin.get(f"{API}/libraries").json()[0]
    assert listed["file_count"] == 3
    assert listed["last_scan_at"] is not None
    assert listed["scanning"] is False

    page = admin.get(f"{API}/libraries/{library['id']}/files").json()
    assert page["total"] == 3
    episode = next(f for f in page["items"] if f["relative_path"] == "Show/S01E01.mkv")
    assert episode["video_codec"] == "h264"
    assert episode["audio_languages"] == ["eng", "fra"]
    assert episode["subtitle_languages"] == ["eng"]

    search = admin.get(f"{API}/libraries/{library['id']}/files", params={"q": "E02"}).json()
    assert [f["relative_path"] for f in search["items"]] == ["Show/S01E02.mkv"]
    # LIKE wildcards in the search are literal.
    literal = admin.get(f"{API}/libraries/{library['id']}/files", params={"q": "100%"}).json()
    assert literal["total"] == 1
    problems = admin.get(f"{API}/libraries/{library['id']}/files", params={"problems": True}).json()
    assert [f["status"] for f in problems["items"]] == ["probe_failed"]

    detail = admin.get(f"{API}/files/{episode['id']}").json()
    assert detail["container"].startswith("matroska")
    kinds = [s["kind"] for s in detail["streams"]]
    assert kinds == ["video", "audio", "audio", "subtitle"]
    assert detail["streams"][3]["forced"] is True


def test_scan_endpoints_404_and_auth(app: FastAPI) -> None:
    admin = admin_client(app)
    assert admin.post(f"{API}/libraries/999/scan").status_code == 404
    assert admin.get(f"{API}/files/999").status_code == 404
    assert TestClient(app).get(f"{API}/libraries/1/files").status_code == 401
