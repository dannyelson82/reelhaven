"""Automatic processing (ADR-0025)."""

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from reelhaven import device_settings
from reelhaven.automation import Automation, FileState, pick, queue_target, rescan_due
from reelhaven.config import Settings
from reelhaven.db import Database, Job, Library
from reelhaven.device_settings import DeviceConfig, DeviceSettings
from reelhaven.devices import CPU
from reelhaven.dryrun import FilePlan
from reelhaven.encode_planner import profile_fingerprint
from reelhaven.encoders import Device
from reelhaven.jobs.queue import JobQueue
from reelhaven.media.probe import probe
from reelhaven.planner import Action, Plan
from reelhaven.profiles import ProfileSettings
from tests.helpers import API
from tests.media_fixtures import FFMPEG, Audio, Spec, make
from tests.test_encode_pipeline import FAST, OLD, app, setup  # noqa: F401 - shared fixture

needs_ffmpeg = pytest.mark.skipif(
    FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed"
)
AUTOMATION_ON = {"paused": False, "rescan_enabled": True, "rescan_at": "03:00"}


def local(day: int, hour: int, minute: int) -> datetime:
    """A naive local time in October 2026: the schedule works in wall-clock time."""
    return datetime(2026, 10, day, hour, minute)  # noqa: DTZ001


# --- pure decisions --------------------------------------------------------------------------


def test_rescan_due() -> None:
    at = "03:00"
    morning = local(8, 3, 30)
    assert rescan_due(None, morning, at)
    assert rescan_due(local(7, 23, 0), morning, at)  # yesterday evening
    assert not rescan_due(local(8, 3, 5), morning, at)  # already done today
    assert not rescan_due(None, local(8, 2, 59), at)  # not time yet
    assert rescan_due(local(8, 2, 0), local(8, 23, 0), at)


def fp(file_id: int, action: Action | None) -> FilePlan:
    plan = (
        None
        if action is None
        else Plan(action=action, tracks=[], flags=[], summary="", details=[], removed_bytes=0)
    )
    return FilePlan(file_id, f"f{file_id}.mkv", 1, "eng", plan)


def test_pick_follows_the_safety_rails() -> None:
    plans = [
        fp(1, "encode"),
        fp(2, "remux"),
        fp(3, "skip"),
        fp(4, None),  # unreadable
        fp(5, "remux"),  # already queued
        fp(6, "remux"),  # failed last time, unchanged
        fp(7, "remux"),  # failed last time, but the file changed since
        fp(8, "encode"),
    ]
    state = FileState(1, 1)
    active = {5}
    gave_up = {6: state, 7: state}
    current = {6: state, 7: FileState(2, 2)}

    def ids(encodes_allowed: bool, limit: int = 10) -> list[int]:
        chosen = pick(
            plans,
            active=active,
            gave_up=gave_up,
            current=current,
            encodes_allowed=encodes_allowed,
            limit=limit,
        )
        return [p.file_id for p in chosen]

    assert ids(encodes_allowed=False) == [2, 7]
    assert ids(encodes_allowed=True) == [1, 2, 7, 8]
    assert ids(encodes_allowed=True, limit=2) == [1, 2]


def test_pick_waits_for_the_original_language() -> None:
    waiting = fp(1, "remux")
    waiting.language_pending = True
    chosen = pick(
        [waiting, fp(2, "remux")],
        active=set(),
        gave_up={},
        current={},
        encodes_allowed=True,
        limit=10,
    )
    assert [p.file_id for p in chosen] == [2]


# --- end to end ------------------------------------------------------------------------------


def add_remux_file(settings: Settings, name: str) -> Path:
    path = settings.media_root / "Movies" / name / "film.mkv"
    path.parent.mkdir(parents=True)
    spec = Spec(codec="libx265", audio=[Audio("eng", default=True), Audio("fre")])
    os.utime(make(path, spec), (OLD, OLD))
    return path


def rescan(application: FastAPI, admin: TestClient, lib: int) -> None:
    admin.post(f"{API}/libraries/{lib}/scan")
    application.state.scanner.wait(lib, timeout=60)
    for title in admin.get(f"{API}/libraries/{lib}/titles").json()["items"]:
        admin.put(f"{API}/titles/{title['id']}/language", json={"language": "eng"})


@needs_ffmpeg
def test_automatic_library_processes_everything(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, big = setup(app, settings, FAST)  # big: needs a re-encode
    small = add_remux_file(settings, "Small (2019)")  # needs track changes only
    rescan(app, admin, lib)
    automation: Automation = app.state.automation

    # Watch mode only: nothing is processed.
    assert admin.patch(f"{API}/libraries/{lib}", json={"watch_mode": "watch"}).status_code == 200
    automation.tick()
    assert app.state.queue.wait_idle(60)
    assert admin.get(f"{API}/jobs").json()["total"] == 0

    # Automatic without an approved test run: only the track changes.
    lib_out = admin.patch(f"{API}/libraries/{lib}", json={"watch_mode": "automatic"}).json()
    assert lib_out["watch_mode"] == "automatic"
    automation.tick()
    assert app.state.queue.wait_idle(120)
    jobs = admin.get(f"{API}/jobs").json()["items"]
    assert [(j["type"], j["status"], j["requested_by"]) for j in jobs] == [
        ("remux", "done", "automatic")
    ]
    assert [a.language for a in probe(small).of_kind("audio")] == ["eng"]
    assert len(probe(big).of_kind("audio")) == 2  # untouched until a test run is approved

    # With the profile approved, the re-encode follows on the next round.
    db: Database = app.state.db
    with db.write() as session:
        library = session.get(Library, lib)
        assert library is not None
        library.test_run_profile = profile_fingerprint(ProfileSettings.model_validate(FAST))
    automation.tick()
    assert app.state.queue.wait_idle(180)
    jobs = admin.get(f"{API}/jobs").json()["items"]
    assert jobs[0]["type"] == "encode" and jobs[0]["status"] == "done", jobs[0]
    automation.tick()  # nothing left
    assert admin.get(f"{API}/jobs").json()["total"] == 2


@needs_ffmpeg
def test_pause_and_no_automatic_retry(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, _big = setup(app, settings, FAST)
    add_remux_file(settings, "Small (2019)")
    rescan(app, admin, lib)
    automation: Automation = app.state.automation

    paused = admin.put(f"{API}/automation", json={**AUTOMATION_ON, "paused": True})
    assert paused.status_code == 200 and admin.get(f"{API}/automation").json()["paused"]
    admin.patch(f"{API}/libraries/{lib}", json={"watch_mode": "automatic"})
    automation.tick()
    assert admin.get(f"{API}/jobs").json()["total"] == 0  # paused: nothing queued

    # Even a manual job waits while paused.
    file_ids = [f["id"] for f in admin.get(f"{API}/libraries/{lib}/files").json()["items"]]
    small_id = next(
        i for i in file_ids if admin.get(f"{API}/files/{i}/plan").json()["action"] == "remux"
    )
    job = admin.post(f"{API}/files/{small_id}/apply").json()
    assert app.state.queue.wait_idle(5)
    assert admin.get(f"{API}/jobs/{job['id']}").json()["status"] == "queued"

    # Cancelled by hand: automation doesn't bring it back.
    admin.post(f"{API}/jobs/{job['id']}/cancel")
    assert admin.put(f"{API}/automation", json=AUTOMATION_ON).status_code == 200
    automation.tick()
    assert app.state.queue.wait_idle(60)
    statuses = [j["status"] for j in admin.get(f"{API}/jobs").json()["items"]]
    assert statuses == ["cancelled"]
    bad = admin.put(f"{API}/automation", json={**AUTOMATION_ON, "rescan_at": "25:00"})
    assert bad.status_code == 422


def test_nightly_rescan_starts_watched_libraries(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    db: Database = app.state.db
    with db.write() as session:
        session.add_all(
            [
                Library(name="Off", type="movies", path="/m/off", watch_mode="off"),
                Library(
                    name="Watched",
                    type="movies",
                    path="/m/w",
                    watch_mode="watch",
                    last_scan_at=datetime(2026, 10, 7, 1, 0, tzinfo=UTC),
                ),
                Library(
                    name="Auto",
                    type="movies",
                    path="/m/a",
                    watch_mode="automatic",
                    last_scan_at=local(8, 3, 10).astimezone(),
                ),
            ]
        )
    started: list[str] = []

    def start(library_id: int) -> bool:
        with db.read() as session:
            library = session.get(Library, library_id)
            assert library is not None
            started.append(library.name)
        return True

    automation = Automation(
        db, start_scan=start, notify_queue=lambda: None, clock=lambda: local(8, 3, 30)
    )
    automation.tick()
    assert started == ["Watched"]  # Off is never scanned; Auto already ran today
    with db.read() as session:
        assert session.scalars(select(Job)).first() is None


# --- keeping every GPU busy (owner request) ------------------------------------------------


def test_queue_target_covers_every_slot_plus_spare() -> None:
    assert queue_target(0) == 4  # no devices known yet: the old minimum
    assert queue_target(2) == 4
    assert queue_target(4) == 6  # RTX + iGPU at 2 each, plus 2 waiting
    assert queue_target(8) == 10


class FakeDevices:
    def __init__(self, *devices: Device) -> None:
        self._devices = devices

    def usable(self) -> list[tuple[Device, object]]:
        return [(d, None) for d in self._devices]


def test_encode_slots_add_up_the_enabled_devices(db: Database, settings: Settings) -> None:
    nvidia = Device(id="nvidia:0", kind="nvidia", name="RTX", family="nvenc", index=0)
    intel = Device(id="intel:0000:00:02.0", kind="intel", name="UHD", family="qsv")
    queue = JobQueue(db, settings, FakeDevices(nvidia, intel, CPU))  # type: ignore[arg-type]
    assert queue.encode_slots() == 4  # 2 + 2; the CPU is off by default
    with db.write() as session:
        device_settings.save(
            session,
            DeviceSettings(
                cpu_enabled=True,
                cpu_concurrency=1,
                devices={
                    nvidia.id: DeviceConfig(concurrency=6),
                    intel.id: DeviceConfig(enabled=False),
                },
            ),
        )
    assert queue.encode_slots() == 7  # 6 on the RTX, the iGPU switched off, 1 on the CPU


@needs_ffmpeg
def test_top_up_fills_every_gpu_slot(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, _big = setup(app, settings, FAST)
    for n in range(9):
        add_remux_file(settings, f"Film {n} (2019)")
    rescan(app, admin, lib)
    # Paused: the app's own Automatic round mustn't queue anything first.
    pause = {"paused": True, "rescan_enabled": False, "rescan_at": "03:00"}
    assert admin.put(f"{API}/automation", json=pause).status_code == 200
    admin.patch(f"{API}/libraries/{lib}", json={"watch_mode": "automatic"})
    db: Database = app.state.db
    automation = Automation(
        db, start_scan=lambda _lib: True, notify_queue=lambda: None, encode_slots=lambda: 6
    )
    assert automation.top_up(lib) == 8  # 6 slots + 2 spare, not the old 4


@needs_ffmpeg
def test_a_finished_job_refills_the_queue_at_once(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, _big = setup(app, settings, FAST)
    add_remux_file(settings, "Small (2019)")
    rescan(app, admin, lib)
    pokes: list[int] = []
    app.state.automation.poke = lambda: pokes.append(1)
    app.state.queue.on_job_finished = app.state.automation.poke  # as wired at startup
    admin.patch(f"{API}/libraries/{lib}", json={"watch_mode": "automatic"})
    app.state.automation.tick()
    assert app.state.queue.wait_idle(120)
    assert pokes  # Automatic was asked to queue more without waiting for the next round


def test_startup_connects_the_queue_to_automatic(app: FastAPI) -> None:  # noqa: F811
    assert app.state.queue.on_job_finished == app.state.automation.poke
