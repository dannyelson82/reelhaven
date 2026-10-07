"""Test runs end to end with the CPU encoder (ADR-0020)."""

import hashlib
import os

import pytest
from fastapi import FastAPI

from reelhaven.config import Settings
from reelhaven.jobs.test_run import frame_times
from reelhaven.quality_metrics import rate, segment_starts
from tests.helpers import API
from tests.media_fixtures import FFMPEG
from tests.test_encode_pipeline import FAST, app, file_id, setup  # noqa: F401 - shared fixture

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


def test_test_run_then_approve(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, path = setup(app, settings, FAST)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    assert admin.get(f"{API}/libraries/{lib}/test-run").json() is None

    started = admin.post(f"{API}/libraries/{lib}/test-run", json={})
    assert started.status_code == 201, started.text
    assert started.json()["file"] == "Film (2020)/film.mkv"
    assert app.state.queue.wait_idle(180)

    run = admin.get(f"{API}/libraries/{lib}/test-run").json()
    assert run["status"] == "done", run
    result = run["result"]
    assert result["bytes_after"] < result["bytes_before"]
    assert result["codec"] == "hevc" and result["bit_depth"] == 10
    assert result["rating"] in ("Indistinguishable", "Very good", "Good", "Visible loss")
    assert result["ssim"] is not None and 0 < result["ssim"] <= 1
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before  # original untouched
    assert admin.get(f"{API}/recycle").json() == []

    frame = admin.get(f"{API}/test-runs/{run['id']}/frames/0/encoded.jpg")
    assert frame.status_code == 200 and frame.headers["content-type"] == "image/jpeg"
    assert frame.content[:2] == b"\xff\xd8"
    assert admin.get(f"{API}/test-runs/{run['id']}/frames/0/other.jpg").status_code == 422
    assert admin.get(f"{API}/test-runs/{run['id']}/frames/99/source.jpg").status_code == 422

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
    assert admin.get(f"{API}/libraries/{lib}/test-run").json()["profile_is_current"] is False


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


def test_only_one_test_run_at_a_time(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, _path = setup(app, settings, FAST)
    app.state.queue.stop()  # keep the first test run waiting
    assert admin.post(f"{API}/libraries/{lib}/test-run", json={}).status_code == 201
    second = admin.post(f"{API}/libraries/{lib}/test-run", json={})
    assert (second.status_code, second.json()["detail"]) == (409, "test_run_in_progress")
