"""End-to-end encodes with the CPU encoder through the whole pipeline."""

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
from reelhaven.db import Database, Library, MediaFile
from reelhaven.devices import CPU, CodecResult, DeviceRegistry, DeviceReport
from reelhaven.encode_planner import profile_fingerprint
from reelhaven.media.probe import probe
from reelhaven.profiles import ProfileSettings
from reelhaven.scanner import Scanner
from tests.helpers import API, admin_client
from tests.media_fixtures import FFMPEG, Audio, Spec, make

pytestmark = pytest.mark.skipif(
    FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed"
)
OLD = time.time() - 3600
BIG = Spec(
    audio=[Audio("eng", default=True), Audio("fre")],
    size="1280x720",
    seconds=3,
    video_bitrate="12M",
)
FAST = {
    "codec": "hevc",
    "quality": 5,
    "speed": "fast",
    "ten_bit": True,
    "max_height": None,
    "audio": "copy",
    "add_stereo_aac": False,
    "min_savings_percent": 10,
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CpuOnly(DeviceRegistry):
    """The real CPU device with fixed capabilities (no 30 s of test encodes per test)."""

    def __init__(self, ffmpeg: str, codecs: tuple[str, ...] = ("hevc", "av1", "h264")) -> None:
        super().__init__(ffmpeg)
        results = [
            CodecResult(codec=c, ten_bit=b, encoder="x", ok=c in codecs)
            for c in ("hevc", "av1", "h264")
            for b in (False, True)
        ]
        report = DeviceReport(CPU.id, CPU.kind, CPU.name, CPU.family, results)
        self._reports = [report]
        self._devices = {CPU.id: CPU}
        self.detected_at = time.time()


@pytest.fixture
def app(settings: Settings) -> Iterator[FastAPI]:
    settings = settings.model_copy(
        update={"transcode_dir": settings.config_dir.parent / "transcode"}
    )
    application = create_app(settings, gateways=frozenset(), detect_devices=False)
    application.state.scanner = Scanner(application.state.db, settings, stable_seconds=0)
    application.state.devices = CpuOnly(FFMPEG or "ffmpeg")
    application.state.queue = type(application.state.queue)(
        application.state.db, settings, application.state.devices
    )
    with TestClient(application):
        yield application


def setup(
    app: FastAPI, settings: Settings, profile: dict[str, Any], cpu: bool = True
) -> tuple[TestClient, int, Path]:
    root = settings.media_root / "Movies"
    path = root / "Film (2020)" / "film.mkv"
    path.parent.mkdir(parents=True)
    os.utime(make(path, BIG), (OLD, OLD))
    admin = admin_client(app)
    admin.put(
        f"{API}/devices/settings", json={"cpu_enabled": cpu, "cpu_concurrency": 1, "devices": {}}
    )
    lib = admin.post(
        f"{API}/libraries", json={"name": "Movies", "type": "movies", "path": "Movies"}
    ).json()
    created = admin.post(f"{API}/profiles", json={"name": "Test", "settings": profile}).json()
    admin.put(f"{API}/libraries/{lib['id']}/profile", json={"profile_id": created["id"]})
    admin.post(f"{API}/libraries/{lib['id']}/scan")
    app.state.scanner.wait(lib["id"], timeout=60)
    for title in admin.get(f"{API}/libraries/{lib['id']}/titles").json()["items"]:
        admin.put(f"{API}/titles/{title['id']}/language", json={"language": "eng"})
    return admin, lib["id"], path


def file_id(admin: TestClient, lib: int) -> int:
    return int(admin.get(f"{API}/libraries/{lib}/files").json()["items"][0]["id"])


def last_job(admin: TestClient) -> dict[str, Any]:
    job: dict[str, Any] = admin.get(f"{API}/jobs").json()["items"][0]
    return job


def test_encode_single_file(app: FastAPI, settings: Settings) -> None:
    admin, lib, path = setup(app, settings, FAST)
    before_hash, before_size = sha(path), path.stat().st_size
    plan = admin.get(f"{API}/files/{file_id(admin, lib)}/plan").json()
    assert plan["action"] == "encode", plan
    assert admin.post(f"{API}/files/{file_id(admin, lib)}/apply").status_code == 201
    assert app.state.queue.wait_idle(180)

    job = last_job(admin)
    assert (job["type"], job["status"], job["outcome"], job["device"]) == (
        "encode",
        "done",
        "replaced",
        "cpu",
    ), job
    info = probe(path)
    assert info.video is not None
    assert (info.video.codec, info.video.bit_depth) == ("hevc", 10)
    assert [a.language for a in info.of_kind("audio")] == ["eng"]  # French dropped in the same pass
    assert path.stat().st_size < before_size * 0.9
    recycled = admin.get(f"{API}/recycle").json()[0]
    with app.state.db.read() as session:
        from reelhaven.db import RecycleItem

        stored = Path(session.get(RecycleItem, recycled["id"]).stored_path)
    assert sha(stored) == before_hash
    # Scratch and work folders are cleaned up.
    assert not any((settings.config_dir.parent / "transcode" / "jobs").glob("*"))
    assert not any((path.parent.parent / ".reelhaven" / "work").glob("*"))
    # Planning again: already done with this profile.
    again = admin.get(f"{API}/files/{file_id(admin, lib)}/plan").json()
    assert again["action"] == "skip"
    assert again["video"]["reason"] == "Already encoded by ReelHaven with this profile."


def test_no_gain_keeps_the_original(app: FastAPI, settings: Settings) -> None:
    """The real result is checked after encoding, whatever the estimate said."""
    admin, lib, path = setup(app, settings, FAST)
    before = sha(path)
    app.state.queue.stop()
    assert admin.post(f"{API}/files/{file_id(admin, lib)}/apply").status_code == 201
    db: Database = app.state.db
    from reelhaven.db import Job

    with db.write() as session:
        job = session.scalars(select(Job)).one()
        job.profile = {**(job.profile or {}), "min_savings_percent": 90}  # unreachable on purpose
    queue = type(app.state.queue)(
        db,
        app.state.settings.model_copy(
            update={"transcode_dir": settings.config_dir.parent / "transcode"}
        ),
        app.state.devices,
    )
    queue.start()
    try:
        assert queue.wait_idle(180)
    finally:
        queue.stop()
    job_out = last_job(admin)
    assert (job_out["status"], job_out["outcome"]) == ("done", "no_gain"), job_out
    assert sha(path) == before
    assert admin.get(f"{API}/recycle").json() == []
    with db.read() as session:
        row = session.scalars(select(MediaFile)).one()
        assert row.no_gain_profile == profile_fingerprint(
            ProfileSettings.model_validate(job.profile)
        )


def test_bulk_encode_needs_a_test_run(app: FastAPI, settings: Settings) -> None:
    admin, lib, _path = setup(app, settings, FAST, cpu=False)
    count = admin.get(f"{API}/libraries/{lib}/dry-run").json()
    total = count["encode"] + count["remux"]
    response = admin.post(f"{API}/libraries/{lib}/apply", json={"expected_count": total})
    assert response.json()["detail"] == "test_run_required"
    db: Database = app.state.db
    with db.write() as session:
        session.execute(
            update(Library).values(
                test_run_profile=profile_fingerprint(ProfileSettings.model_validate(FAST))
            )
        )
    assert admin.post(f"{API}/libraries/{lib}/apply", json={"expected_count": total}).json() == {
        "queued": 1
    }


def test_disabled_or_incapable_device_leaves_job_queued(app: FastAPI, settings: Settings) -> None:
    admin, lib, path = setup(app, settings, {**FAST, "codec": "av1"})
    app.state.queue.stop()
    app.state.devices = CpuOnly(FFMPEG or "ffmpeg", codecs=("hevc",))  # no AV1 here
    queue = type(app.state.queue)(
        app.state.db,
        settings.model_copy(update={"transcode_dir": settings.config_dir.parent / "transcode"}),
        app.state.devices,
    )
    queue.start()
    try:
        before = sha(path)
        admin.post(f"{API}/files/{file_id(admin, lib)}/apply")
        queue.notify()
        assert queue.wait_idle(15)  # nothing runnable: returns without running the job
        assert last_job(admin)["status"] == "queued"
        assert sha(path) == before
    finally:
        queue.stop()


def test_remember_no_gain_per_profile(db: Database) -> None:
    from reelhaven.encode_planner import plan_video
    from reelhaven.media.info import MediaInfo, Stream

    info = MediaInfo(
        container="matroska",
        duration_s=100,
        size_bytes=200_000_000,
        bit_rate=None,
        streams=[
            Stream(
                index=0,
                kind="video",
                codec="h264",
                width=1920,
                height=1080,
                frame_rate=24,
                bit_rate=15_000_000,
            )
        ],
    )
    profile = ProfileSettings()
    assert plan_video(info, profile).decision == "encode"
    assert plan_video(info, profile, profile_fingerprint(profile)).decision == "keep"
    assert (
        plan_video(info, ProfileSettings(quality=7), profile_fingerprint(profile)).decision
        == "encode"
    )
    with db.read() as session:
        assert session.scalars(select(MediaFile)).all() == []


@pytest.mark.parametrize("codec", ["eac3", "aac", "opus"])
def test_encode_converts_audio(app: FastAPI, settings: Settings, codec: str) -> None:
    """ADR-0023: lossless surround is converted, small lossy stereo is copied."""
    admin, lib, path = setup(app, settings, {**FAST, "audio": "convert", "audio_codec": codec})
    path.unlink()
    surround = Audio("eng", default=True, channels=6, codec="flac", bps=4_000_000)
    os.utime(make(path, Spec(audio=[surround, Audio("eng")], size="1280x720",
                             seconds=3, video_bitrate="12M")), (OLD, OLD))  # fmt: skip
    admin.post(f"{API}/libraries/{lib}/scan")
    app.state.scanner.wait(lib, timeout=60)
    assert admin.post(f"{API}/files/{file_id(admin, lib)}/apply").status_code == 201
    assert app.state.queue.wait_idle(180)
    job = last_job(admin)
    assert (job["status"], job["outcome"]) == ("done", "replaced"), job
    audio = probe(path).of_kind("audio")
    assert [a.codec for a in audio] == [codec, "aac"]
    assert audio[0].channels == 6
    assert audio[0].bit_rate != 4_000_000  # the old track's statistics are gone
    again = admin.get(f"{API}/files/{file_id(admin, lib)}/plan").json()
    assert again["action"] == "skip", again  # nothing converted twice
