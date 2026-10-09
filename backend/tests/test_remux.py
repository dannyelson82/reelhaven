"""End-to-end tests of the only code that changes media files.

Real ffmpeg, real (tiny, generated) files. Every failure path must leave the
original byte-for-byte untouched.
"""

import hashlib
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from reelhaven.app import create_app
from reelhaven.config import Settings
from reelhaven.db import AuditLog, Database, Job, RecycleItem, Title
from reelhaven.db.types import utcnow
from reelhaven.jobs import pipeline, replace
from reelhaven.jobs.commands import MARKER_TAG, expected_remux_codecs, remux_command
from reelhaven.media.info import MediaInfo, Stream
from reelhaven.media.probe import probe, probe_raw
from reelhaven.planner import plan
from reelhaven.policy import LanguagePolicy
from reelhaven.scanner import Scanner
from tests.helpers import API, admin_client
from tests.media_fixtures import FFMPEG, Audio, Spec, Sub, make

pytestmark = pytest.mark.skipif(
    FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed"
)
OLD = time.time() - 3600

MULTI = Spec(
    audio=[
        Audio("eng", "English", default=True),
        Audio("eng", "Commentary", comment=True),
        Audio("fre", "French"),
        Audio("ger", "German"),
    ],
    subs=[
        Sub("eng", "English"),
        Sub("eng", "Forced", forced=True, default=True),
        Sub("fre", "French"),
    ],
    seconds=3,
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- command builder (golden) ----------------------------------------------------------


def test_remux_command_golden() -> None:
    info = MediaInfo(
        container="matroska,webm",
        duration_s=10,
        size_bytes=1,
        bit_rate=None,
        streams=[
            Stream(index=0, kind="video", codec="h264"),
            Stream(index=1, kind="audio", language="eng", default=False, dispositions=[]),
            Stream(index=2, kind="audio", language="fra", default=True, dispositions=["default"]),
            Stream(index=3, kind="subtitle", language="eng", forced=True, dispositions=["forced"]),
            Stream(index=4, kind="attachment", codec="ttf"),
        ],
    )
    p = plan(info, "eng", LanguagePolicy())
    args = remux_command("ffmpeg", Path("/m/a.mkv"), Path("/m/.reelhaven/work/1/a.mkv"), info, p)
    assert args == [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-nostats",
        "-i",
        "file:/m/a.mkv",
        "-map",
        "0:0",
        "-map",
        "0:1",
        "-map",
        "0:3",
        "-map",
        "0:4",
        "-map_metadata",
        "0",
        "-map_chapters",
        "0",
        "-c",
        "copy",
        "-disposition:1",
        "default",
        "-disposition:2",
        "default+forced",
        "-metadata",
        f"{MARKER_TAG}=remux-1",
        "-f",
        "matroska",
        "file:/m/.reelhaven/work/1/a.mkv",
    ]


def test_remux_refuses_container_change() -> None:
    info = MediaInfo(container="mp4", duration_s=1, size_bytes=1, bit_rate=None, streams=[])
    p = plan(info, None, LanguagePolicy())
    with pytest.raises(ValueError):
        remux_command("ffmpeg", Path("/m/a.mp4"), Path("/m/a.mkv"), info, p)
    with pytest.raises(ValueError, match="isn't supported"):
        remux_command("ffmpeg", Path("/m/a.avi"), Path("/m/b.avi"), info, p)


# --- end to end --------------------------------------------------------------------------


@pytest.fixture
def app(settings: Settings) -> Iterator[FastAPI]:
    application = create_app(settings, gateways=frozenset(), detect_devices=False)
    application.state.scanner = Scanner(
        application.state.db,
        settings,
        stable_seconds=0,
        resolve_languages=application.state.scanner._resolve_languages,
    )
    with TestClient(application):
        yield application


def setup_library(
    app: FastAPI, settings: Settings, files: dict[str, Spec]
) -> tuple[TestClient, int, Path]:
    root = settings.media_root / "Movies"
    for rel, spec in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        os.utime(make(root / rel, spec), (OLD, OLD))
    admin = admin_client(app)
    lib = admin.post(
        f"{API}/libraries", json={"name": "Movies", "type": "movies", "path": "Movies"}
    ).json()
    admin.post(f"{API}/libraries/{lib['id']}/scan")
    app.state.scanner.wait(lib["id"], timeout=60)
    for title in admin.get(f"{API}/libraries/{lib['id']}/titles").json()["items"]:
        admin.put(f"{API}/titles/{title['id']}/language", json={"language": "eng"})
    return admin, lib["id"], root


def apply_all(app: FastAPI, admin: TestClient, lib: int) -> dict[str, Any]:
    count = admin.get(f"{API}/libraries/{lib}/dry-run").json()["remux"]
    result = admin.post(f"{API}/libraries/{lib}/apply", json={"expected_count": count})
    assert result.status_code == 200, result.text
    assert app.state.queue.wait_idle(timeout=120)
    body: dict[str, Any] = result.json()
    return body


def jobs(admin: TestClient) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = admin.get(f"{API}/jobs").json()["items"]
    return items


def test_remux_mkv_end_to_end(app: FastAPI, settings: Settings) -> None:
    admin, lib, root = setup_library(app, settings, {"Film (2020)/film.mkv": MULTI})
    path = root / "Film (2020)" / "film.mkv"
    before = sha(path)
    size_before = path.stat().st_size

    assert apply_all(app, admin, lib) == {"queued": 1, "waiting": 0}
    job = jobs(admin)[0]
    assert job["status"] == "done", job["error"]
    assert job["bytes_before"] == size_before
    assert job["bytes_after"] == path.stat().st_size < size_before

    info = probe(path)
    audio = info.of_kind("audio")
    subs = info.of_kind("subtitle")
    assert [(a.language, a.default, a.commentary) for a in audio] == [
        ("eng", True, False),
        ("eng", False, True),
    ]
    assert [(s.language, s.forced, s.default) for s in subs] == [
        ("eng", False, False),
        ("eng", True, True),
    ]
    assert probe_raw(path)["format"]["tags"].get(MARKER_TAG) == "remux-1"

    # The original is in the recycle bin, byte for byte, on the library's disk.
    item = admin.get(f"{API}/recycle").json()[0]
    with app.state.db.read() as session:
        row = session.scalars(select(RecycleItem)).one()
        assert sha(Path(row.stored_path)) == before
        assert Path(row.stored_path).is_relative_to(root / ".reelhaven" / "recycle")
    assert item["original_path"] == str(path.resolve())
    assert not (root / ".reelhaven" / "work" / str(job["id"])).exists()

    # Idempotent on the real file: nothing left to do.
    assert admin.get(f"{API}/libraries/{lib}/dry-run").json()["remux"] == 0

    # Restore puts the original back; the remuxed file is recycled, not lost.
    after = sha(path)
    restored = admin.post(f"{API}/recycle/{item['id']}/restore")
    assert restored.status_code == 200, restored.text
    assert sha(path) == before
    active = admin.get(f"{API}/recycle").json()
    assert [(i["reason"]) for i in active] == ["restore-swap"]
    with app.state.db.read() as session:
        swap = session.scalars(
            select(RecycleItem).where(RecycleItem.reason == "restore-swap")
        ).one()
        assert sha(Path(swap.stored_path)) == after
        actions = [a.action for a in session.scalars(select(AuditLog))]
    assert {"library.apply", "file.replaced", "recycle.restored"} <= set(actions)

    # Purge deletes the stored copy for good.
    assert admin.delete(f"{API}/recycle/{active[0]['id']}").status_code == 204
    assert not Path(swap.stored_path).exists()
    assert admin.get(f"{API}/recycle").json() == []


def test_remux_mp4(app: FastAPI, settings: Settings) -> None:
    spec = Spec(
        audio=[Audio("eng", default=True), Audio("spa")], subs=[Sub("eng"), Sub("spa")], seconds=2
    )
    admin, lib, root = setup_library(app, settings, {"Clip (2021)/clip.mp4": spec})
    apply_all(app, admin, lib)
    assert jobs(admin)[0]["status"] == "done", jobs(admin)[0]["error"]
    info = probe(root / "Clip (2021)" / "clip.mp4")
    assert [s.language for s in info.streams if s.kind != "video"] == ["eng", "eng"]


def test_hostile_filename_end_to_end(app: FastAPI, settings: Settings) -> None:
    name = "$(touch pwned) -i ; rm -rf x.mkv"
    admin, lib, root = setup_library(app, settings, {f"Bad (2020)/{name}": MULTI})
    apply_all(app, admin, lib)
    assert jobs(admin)[0]["status"] == "done", jobs(admin)[0]["error"]
    assert (root / "Bad (2020)" / name).exists()
    assert not any(p.name == "pwned" for p in settings.media_root.rglob("*"))


def assert_failed_untouched(admin: TestClient, path: Path, digest: str, message: str) -> None:
    job = jobs(admin)[0]
    assert job["status"] == "failed"
    assert message in (job["error"] or "")
    assert sha(path) == digest
    assert admin.get(f"{API}/recycle").json() == []
    assert (
        not list((path.parent.parent / ".reelhaven" / "work").glob("*/*"))
        if (path.parent.parent / ".reelhaven" / "work").exists()
        else True
    )


def test_source_changed_after_planning(app: FastAPI, settings: Settings) -> None:
    admin, lib, root = setup_library(app, settings, {"Film (2020)/film.mkv": MULTI})
    path = root / "Film (2020)" / "film.mkv"
    app.state.queue.stop()  # hold the worker so we can change the file first
    count = admin.get(f"{API}/libraries/{lib}/dry-run").json()["remux"]
    admin.post(f"{API}/libraries/{lib}/apply", json={"expected_count": count})
    with path.open("ab") as handle:
        handle.write(b"\0")  # e.g. Sonarr upgraded the file meanwhile
    digest = sha(path)
    app.state.queue = type(app.state.queue)(app.state.db, settings)
    app.state.queue.start()
    assert app.state.queue.wait_idle(60)
    assert_failed_untouched(admin, path, digest, "changed since it was planned")


def test_verification_failure_leaves_original(
    app: FastAPI, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin, lib, root = setup_library(app, settings, {"Film (2020)/film.mkv": MULTI})
    path = root / "Film (2020)" / "film.mkv"
    digest = sha(path)
    monkeypatch.setattr(pipeline, "expected_layout", lambda *a: [("video", None, None)])
    apply_all(app, admin, lib)
    assert_failed_untouched(admin, path, digest, "expected 1 streams")


def test_different_filesystems_refused(
    app: FastAPI, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin, lib, root = setup_library(app, settings, {"Film (2020)/film.mkv": MULTI})
    path = root / "Film (2020)" / "film.mkv"
    digest = sha(path)
    monkeypatch.setattr(replace, "_same_device", lambda *paths: False)
    apply_all(app, admin, lib)
    assert_failed_untouched(admin, path, digest, "same disk")


def test_failed_final_rename_puts_original_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = tmp_path / "film.mkv"
    original.write_bytes(b"original")
    output = tmp_path / "work" / "film.mkv"
    output.parent.mkdir()
    output.write_bytes(b"new")
    st = original.stat()
    real_rename = Path.rename
    calls = {"n": 0}

    def flaky_rename(self: Path, target: Any) -> Path:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", flaky_rename)
    with pytest.raises(replace.ReplaceError, match="disk full"):
        replace.replace_with(
            original,
            output,
            tmp_path / "recycle" / "film.mkv",
            replace.Snapshot(st.st_size, st.st_mtime_ns),
        )
    assert original.read_bytes() == b"original"
    assert not (tmp_path / "recycle" / "film.mkv").exists()


def test_cancel_queued_job(app: FastAPI, settings: Settings) -> None:
    admin, lib, root = setup_library(app, settings, {"Film (2020)/film.mkv": MULTI})
    path = root / "Film (2020)" / "film.mkv"
    digest = sha(path)
    app.state.queue.stop()
    count = admin.get(f"{API}/libraries/{lib}/dry-run").json()["remux"]
    admin.post(f"{API}/libraries/{lib}/apply", json={"expected_count": count})
    job = jobs(admin)[0]
    assert admin.post(f"{API}/jobs/{job['id']}/cancel").json()["status"] == "cancelled"
    assert admin.post(f"{API}/jobs/{job['id']}/cancel").status_code == 409
    app.state.queue = type(app.state.queue)(app.state.db, settings)
    app.state.queue.start()
    assert app.state.queue.wait_idle(30)
    assert jobs(admin)[0]["status"] == "cancelled"
    assert sha(path) == digest

    retried = admin.post(f"{API}/jobs/{job['id']}/retry")
    assert retried.status_code == 201
    assert app.state.queue.wait_idle(60)
    assert jobs(admin)[0]["status"] == "done"


def test_startup_recovers_interrupted_jobs(app: FastAPI, settings: Settings) -> None:
    admin, lib, root = setup_library(app, settings, {"Film (2020)/film.mkv": MULTI})
    app.state.queue.stop()
    count = admin.get(f"{API}/libraries/{lib}/dry-run").json()["remux"]
    admin.post(f"{API}/libraries/{lib}/apply", json={"expected_count": count})
    db: Database = app.state.db
    with db.write() as session:
        session.execute(update(Job).values(status="running", progress=0.5))
    leftover = root / ".reelhaven" / "work" / "1" / "film.mkv"
    leftover.parent.mkdir(parents=True)
    leftover.write_bytes(b"partial")
    queue = type(app.state.queue)(db, settings)
    queue.start()  # simulates a container restart
    assert queue.wait_idle(60)
    assert jobs(admin)[0]["status"] == "done"
    assert not leftover.exists()
    queue.stop()


def test_apply_guards(app: FastAPI, settings: Settings) -> None:
    spec = Spec(audio=[Audio("eng", default=True)], subs=[Sub("eng")], seconds=1)
    admin, lib, _root = setup_library(
        app, settings, {"Film (2020)/film.mkv": MULTI, "Done (2020)/d.mkv": spec}
    )
    app.state.queue.stop()
    # Stale confirmation: the user saw a different number.
    assert (
        admin.post(f"{API}/libraries/{lib}/apply", json={"expected_count": 5}).json()["detail"]
        == "plan_changed"
    )
    files = {
        f["relative_path"]: f["id"]
        for f in admin.get(f"{API}/libraries/{lib}/files").json()["items"]
    }
    assert (
        admin.post(f"{API}/files/{files['Done (2020)/d.mkv']}/apply").json()["detail"]
        == "nothing_to_do"
    )
    assert admin.post(f"{API}/files/{files['Film (2020)/film.mkv']}/apply").status_code == 201
    assert (
        admin.post(f"{API}/files/{files['Film (2020)/film.mkv']}/apply").json()["detail"]
        == "already_queued"
    )
    # Scripts with the API key can't change files.
    key = admin.post(f"{API}/settings/security/api-key").json()["api_key"]
    script = TestClient(app)
    assert (
        script.post(
            f"{API}/libraries/{lib}/apply", json={"expected_count": 1}, headers={"X-Api-Key": key}
        ).status_code
        == 403
    )


def test_expired_recycle_items_are_purged(app: FastAPI, settings: Settings) -> None:
    from reelhaven.jobs.service import purge_expired

    admin, lib, root = setup_library(app, settings, {"Film (2020)/film.mkv": MULTI})
    apply_all(app, admin, lib)
    db: Database = app.state.db
    with db.write() as session:
        item = session.scalars(select(RecycleItem)).one()
        stored = Path(item.stored_path)
        item.expires_at = utcnow()
    assert stored.exists()
    assert purge_expired(db) == 1
    assert not stored.exists()
    assert not (root / ".reelhaven" / "recycle" / "job-1").exists()  # empty folders removed


def test_restore_refuses_paths_outside_the_library(tmp_path: Path) -> None:
    root = tmp_path / "lib"
    (root / ".reelhaven" / "recycle").mkdir(parents=True)
    stored = root / ".reelhaven" / "recycle" / "x.mkv"
    stored.write_bytes(b"x")
    outside = tmp_path / "elsewhere" / "x.mkv"
    with pytest.raises(replace.ReplaceError, match="outside the library"):
        replace.restore(stored, outside, root / ".reelhaven" / "recycle" / "y.mkv", root)
    with pytest.raises(replace.ReplaceError, match="outside the library"):
        replace.restore(outside, root / "x.mkv", root / ".reelhaven" / "recycle" / "y.mkv", root)
    assert stored.exists()


def test_remux_converts_planned_audio_tracks() -> None:
    """ADR-0023: only the converted track gets an encoder; video and the rest are copied."""
    info = MediaInfo(
        container="matroska,webm",
        duration_s=10,
        size_bytes=1,
        bit_rate=None,
        streams=[
            Stream(index=0, kind="video", codec="hevc"),
            Stream(index=1, kind="audio", codec="ac3", language="eng", default=True),
            Stream(index=2, kind="audio", codec="truehd", language="eng", channels=6),
        ],
    )
    p = plan(info, "eng", LanguagePolicy())
    p.tracks[1].convert_codec, p.tracks[1].convert_kbps = "opus", 288
    args = remux_command("ffmpeg", Path("/m/a.mkv"), Path("/m/w/a.mkv"), info, p)
    tail = args[args.index("-c") : args.index("-metadata", args.index("-c"))]
    assert "-c:a:1" in tail and "-c:a:0" not in tail
    assert tail[tail.index("-c:a:1") : tail.index("-c:a:1") + 6] == [
        "-c:a:1", "libopus", "-b:a:1", "288k", "-mapping_family:a:1", "1",
    ]  # fmt: skip
    assert args[args.index("-metadata:s:2") :][:2] == ["-metadata:s:2", "BPS="]
    assert expected_remux_codecs(Path("/m/a.mkv"), info, p) == {2: ("opus", None)}
    p.tracks[1].convert_channels = 2
    args = remux_command("ffmpeg", Path("/m/a.mkv"), Path("/m/w/a.mkv"), info, p)
    assert args[args.index("-ac:a:1") + 1] == "2"
    assert expected_remux_codecs(Path("/m/a.mkv"), info, p) == {2: ("opus", 2)}


def test_files_wait_until_their_language_is_looked_up(app: FastAPI, settings: Settings) -> None:
    admin, lib, _root = setup_library(app, settings, {"Film (2020)/film.mkv": MULTI})
    db: Database = app.state.db
    # As if the scan were still running, or Sonarr/Radarr/TMDB couldn't be reached:
    # planned without the original language, the French track could be lost.
    with db.write() as session:
        session.execute(
            update(Title).values(
                resolved_at=None, language_source="unknown", original_language=None
            )
        )
    dry = admin.get(f"{API}/libraries/{lib}/dry-run").json()
    assert (dry["remux"], dry["waiting_for_language"]) == (1, 1)
    assert dry["items"][0]["language_pending"] is True
    file_id = dry["items"][0]["file_id"]

    refused = admin.post(f"{API}/files/{file_id}/apply")
    assert (refused.status_code, refused.json()["detail"]) == (409, "language_pending")
    assert admin.post(f"{API}/libraries/{lib}/apply", json={"expected_count": 1}).json() == {
        "queued": 0,
        "waiting": 1,
    }
    assert jobs(admin) == []

    # Once the lookup has run (here: no integrations, so "unknown"), it can go ahead.
    admin.post(f"{API}/libraries/{lib}/languages/refresh")
    app.state.scanner.wait(lib, timeout=60)
    dry = admin.get(f"{API}/libraries/{lib}/dry-run").json()
    assert dry["waiting_for_language"] == 0
    assert apply_all(app, admin, lib) == {"queued": 1, "waiting": 0}


def test_forced_english_subtitles_get_default_and_forced_flags(
    app: FastAPI, settings: Settings
) -> None:
    """Owner request: 'Forced' only in the title isn't enough for players to show it."""
    spec = Spec(
        audio=[Audio("eng", "English", default=True)],
        subs=[Sub("eng", "English"), Sub("eng", "English Forced")],
    )
    admin, lib, root = setup_library(app, settings, {"Film (2020)/film.mkv": spec})
    path = root / "Film (2020)" / "film.mkv"
    before = [s for s in probe(path).streams if s.kind == "subtitle"]
    assert [s.dispositions for s in before] == [[], []]  # no flags at all

    assert apply_all(app, admin, lib) == {"queued": 1, "waiting": 0}
    assert jobs(admin)[0]["status"] == "done", jobs(admin)[0]["error"]
    after = [s for s in probe(path).streams if s.kind == "subtitle"]
    assert "forced" in after[1].dispositions and "default" in after[1].dispositions
    assert "forced" not in after[0].dispositions
    # A rescan finds nothing left to do.
    admin.post(f"{API}/libraries/{lib}/scan")
    app.state.scanner.wait(lib, timeout=60)
    assert admin.get(f"{API}/libraries/{lib}/dry-run").json()["remux"] == 0
