"""Test runs end to end with the CPU encoder (ADR-0020)."""

import hashlib
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from reelhaven.config import Settings
from reelhaven.db import Database, Job, TestRun, TestRunSample
from reelhaven.jobs.test_run import frame_times, run_status, sample_status
from reelhaven.media.probe import probe
from reelhaven.quality_metrics import rate, segment_starts
from tests.helpers import API
from tests.media_fixtures import FFMPEG, Audio, Spec, make
from tests.test_encode_pipeline import (  # noqa: F401 - shared fixture
    BIG,
    FAST,
    OLD,
    app,
    file_id,
    setup,
)

pytestmark = pytest.mark.skipif(
    FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed"
)


def test_rating_bands() -> None:
    assert rate(41, None) == "Indistinguishable"
    assert rate(37, 0.5) == "Very good"  # XPSNR wins when available
    assert rate(34, None) == "Good"
    assert rate(30, None) == "Visible loss"
    assert rate(None, 0.99) == "Indistinguishable"
    assert rate(None, 0.94) == "Visible loss"
    assert rate(None, None) == "Unknown"


def test_segments_and_frame_times() -> None:
    assert segment_starts(5) == [0.0]
    assert segment_starts(100) == [22.5, 45.0, 67.5]
    assert frame_times(3) == [1.5]  # inside a short video
    assert frame_times(100) == [27.5, 50.0, 72.5]


def test_status_rules() -> None:
    run = TestRun(status="running")
    sample = TestRunSample(status="running")
    assert sample_status(sample, "queued") == "running"
    assert sample_status(sample, "cancelled") == "failed"  # cancelled before it started
    assert sample_status(TestRunSample(status="done"), "done") == "done"
    assert run_status(run, ["running", "done"]) == "running"
    assert run_status(run, ["done", "done"]) == "done"
    assert run_status(run, ["done", "failed"]) == "failed"
    assert run_status(run, []) == "running"
    assert run_status(TestRun(status="approved"), ["done"]) == "approved"


def add_film(
    admin: TestClient,
    app: FastAPI,  # noqa: F811
    settings: Settings,
    lib: int,
    name: str,
    spec: Spec = BIG,
) -> Path:
    path = settings.media_root / "Movies" / name / "film.mkv"
    path.parent.mkdir(parents=True)
    os.utime(make(path, spec), (OLD, OLD))
    admin.post(f"{API}/libraries/{lib}/scan")
    app.state.scanner.wait(lib, timeout=60)
    for title in admin.get(f"{API}/libraries/{lib}/titles").json()["items"]:
        admin.put(f"{API}/titles/{title['id']}/language", json={"language": "eng"})
    return path


def test_test_run_then_approve(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, path = setup(app, settings, FAST)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    assert admin.get(f"{API}/libraries/{lib}/test-run").json() == {"samples": 1, "run": None}

    started = admin.post(f"{API}/libraries/{lib}/test-run", json={})
    assert started.status_code == 201, started.text
    assert [s["file"] for s in started.json()["samples"]] == ["Film (2020)/film.mkv"]
    assert app.state.queue.wait_idle(180)

    run = admin.get(f"{API}/libraries/{lib}/test-run").json()["run"]
    assert run["status"] == "done", run
    (sample,) = run["samples"]
    result = sample["result"]
    assert sample["status"] == "done" and sample["progress"] == 1.0
    assert result["bytes_after"] < result["bytes_before"]
    assert result["codec"] == "hevc" and result["bit_depth"] == 10
    assert result["rating"] in ("Indistinguishable", "Very good", "Good", "Visible loss")
    assert result["ssim"] is not None and 0 < result["ssim"] <= 1
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before  # original untouched
    assert admin.get(f"{API}/recycle").json() == []

    frames = f"{API}/test-run-samples/{sample['id']}/frames"
    frame = admin.get(f"{frames}/0/encoded.jpg")
    assert frame.status_code == 200 and frame.headers["content-type"] == "image/jpeg"
    assert frame.content[:2] == b"\xff\xd8"
    assert admin.get(f"{frames}/0/other.jpg").status_code == 422
    assert admin.get(f"{frames}/99/source.jpg").status_code == 422
    assert admin.get(f"{API}/test-run-samples/999/frames/0/source.jpg").status_code == 404

    # Bulk encoding is locked until the owner approves.
    dry = admin.get(f"{API}/libraries/{lib}/dry-run").json()
    total = dry["encode"] + dry["remux"]
    assert (
        admin.post(f"{API}/libraries/{lib}/apply", json={"expected_count": total}).json()["detail"]
        == "test_run_required"
    )
    approved = admin.post(f"{API}/test-runs/{run['id']}/approve").json()
    assert approved["status"] == "approved" and approved["approved_by"] == "admin"
    assert (
        admin.post(f"{API}/libraries/{lib}/apply", json={"expected_count": total}).status_code
        == 200
    )

    # Changing the profile invalidates the approval.
    profiles = admin.get(f"{API}/profiles").json()
    mine = next(p for p in profiles if p["name"] == "Test")
    admin.put(
        f"{API}/profiles/{mine['id']}", json={"name": "Test", "settings": {**FAST, "quality": 7}}
    )
    run = admin.get(f"{API}/libraries/{lib}/test-run").json()["run"]
    assert run["profile_is_current"] is False


def test_several_samples(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, _path = setup(app, settings, FAST)
    add_film(admin, app, settings, lib, "Other (2021)")
    started = admin.post(f"{API}/libraries/{lib}/test-run", json={"samples": 3})
    assert started.status_code == 201, started.text
    files = sorted(s["file"] for s in started.json()["samples"])
    assert files == ["Film (2020)/film.mkv", "Other (2021)/film.mkv"]  # only two candidates
    assert app.state.queue.wait_idle(300)
    state = admin.get(f"{API}/libraries/{lib}/test-run").json()
    assert state["samples"] == 3  # remembered for next time
    assert state["run"]["status"] == "done"
    assert all(s["status"] == "done" for s in state["run"]["samples"])
    folder = app.state.settings.transcode_dir / "test-run" / str(lib) / str(state["run"]["id"])
    assert len([p for p in folder.iterdir() if p.is_dir()]) == 2

    # A new run replaces the old one on disk.
    first = state["run"]["id"]
    one = admin.post(f"{API}/libraries/{lib}/test-run", json={"file_id": file_id(admin, lib)})
    assert len(one.json()["samples"]) == 1
    assert app.state.queue.wait_idle(180)
    assert not (app.state.settings.transcode_dir / "test-run" / str(lib) / str(first)).exists()
    assert admin.get(f"{API}/libraries/{lib}/test-run").json()["samples"] == 3


def test_cancelled_sample_fails_the_run(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, _path = setup(app, settings, FAST)
    app.state.queue.stop()  # keep the job queued
    run = admin.post(f"{API}/libraries/{lib}/test-run", json={}).json()
    assert admin.post(f"{API}/jobs/{run['samples'][0]['job_id']}/cancel").status_code == 200
    state = admin.get(f"{API}/libraries/{lib}/test-run").json()["run"]
    assert state["status"] == "failed"
    assert state["samples"][0]["error"] == "Cancelled."
    approve = admin.post(f"{API}/test-runs/{run['id']}/approve")
    assert approve.json()["detail"] == "test_run_not_passed"
    # Retrying the test job would be a real encode: start a new test run instead.
    retry = admin.post(f"{API}/jobs/{run['samples'][0]['job_id']}/retry")
    assert (retry.status_code, retry.json()["detail"]) == (409, "test_run_job")
    # A failed run doesn't block a new one.
    assert admin.post(f"{API}/libraries/{lib}/test-run", json={}).status_code == 201


def test_test_run_needs_a_profile_and_candidates(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, _path = setup(app, settings, FAST)
    admin.put(f"{API}/libraries/{lib}/profile", json={"profile_id": None})
    assert admin.post(f"{API}/libraries/{lib}/test-run", json={}).json()["detail"] == "no_profile"
    profiles = admin.get(f"{API}/profiles").json()
    mine = next(p for p in profiles if p["name"] == "Test")
    admin.put(f"{API}/libraries/{lib}/profile", json={"profile_id": mine["id"]})
    other = file_id(admin, lib) + 999
    assert (
        admin.post(f"{API}/libraries/{lib}/test-run", json={"file_id": other}).json()["detail"]
        == "not_an_encode_candidate"
    )
    for samples in (0, 6):
        bad = admin.post(f"{API}/libraries/{lib}/test-run", json={"samples": samples})
        assert bad.status_code == 422


def test_only_one_test_run_at_a_time(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, _path = setup(app, settings, FAST)
    app.state.queue.stop()  # keep the first test run waiting
    assert admin.post(f"{API}/libraries/{lib}/test-run", json={}).status_code == 201
    second = admin.post(f"{API}/libraries/{lib}/test-run", json={})
    assert (second.status_code, second.json()["detail"]) == (409, "test_run_in_progress")


def test_track_changes_need_no_test_run(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    """ADR-0020: only re-encoding is gated; track changes can be applied right away."""
    admin, lib, big = setup(app, settings, FAST)
    small = add_film(
        admin,
        app,
        settings,
        lib,
        "Small (2019)",
        Spec(codec="libx265", audio=[Audio("eng", default=True), Audio("fre")]),
    )
    dry = admin.get(f"{API}/libraries/{lib}/dry-run").json()
    assert (dry["encode"], dry["remux"]) == (1, 1), dry
    everything = admin.post(f"{API}/libraries/{lib}/apply", json={"expected_count": 2})
    assert everything.json()["detail"] == "test_run_required"

    tracks = admin.post(
        f"{API}/libraries/{lib}/apply", json={"expected_count": 1, "only_track_changes": True}
    )
    assert tracks.status_code == 200, tracks.text
    assert tracks.json()["queued"] == 1
    assert app.state.queue.wait_idle(120)
    assert [a.language for a in probe(small).of_kind("audio")] == ["eng"]
    assert len(probe(big).of_kind("audio")) == 2  # waits for the test run


def test_samples_run_one_at_a_time(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    """Owner request: the first result shows while the next file encodes."""
    admin, lib, _path = setup(app, settings, FAST)
    add_film(admin, app, settings, lib, "Other (2021)")
    # Two CPU slots: without the rule both samples would run together.
    admin.put(
        f"{API}/devices/settings", json={"cpu_enabled": True, "cpu_concurrency": 2, "devices": {}}
    )
    started = admin.post(f"{API}/libraries/{lib}/test-run", json={"samples": 2})
    assert started.status_code == 201, started.text
    assert app.state.queue.wait_idle(300)
    db: Database = app.state.db
    with db.read() as session:
        runs = sorted(
            (job.started_at, job.finished_at)
            for job in session.scalars(select(Job).where(Job.type == "test"))
        )
    assert len(runs) == 2 and all(start and end for start, end in runs)
    (_first_start, first_end), (second_start, _second_end) = runs
    assert first_end is not None and second_start is not None
    assert second_start >= first_end  # the second began after the first finished
