"""Backend support for the setup wizard (ADR-0026)."""

from fastapi import FastAPI

from reelhaven.config import Settings
from reelhaven.scanner import ScanProgress
from tests.helpers import API
from tests.test_encode_pipeline import FAST, app, setup  # noqa: F401 - shared fixture


def test_estimate_compares_profiles_without_changing_anything(
    app: FastAPI,  # noqa: F811
    settings: Settings,
) -> None:
    admin, lib, _path = setup(app, settings, FAST)  # one big H.264 file
    before = admin.get(f"{API}/libraries/{lib}/profile").json()
    body = {
        "profiles": {
            "smallest": {**FAST, "quality": 2},
            "balanced": {**FAST, "quality": 6},
            "best": {**FAST, "quality": 9},
            "none": None,
        }
    }
    got = admin.post(f"{API}/libraries/{lib}/estimate", json=body)
    assert got.status_code == 200, got.text
    out = got.json()
    assert out["library_bytes"] > 0
    r = out["results"]
    assert {k: r[k]["encode"] for k in r} == {"smallest": 1, "balanced": 1, "best": 1, "none": 0}
    assert r["smallest"]["saved_bytes"] > r["balanced"]["saved_bytes"] > r["best"]["saved_bytes"]
    assert r["none"]["saved_bytes"] == 0
    # Read-only: the library's profile and the queue are untouched.
    assert admin.get(f"{API}/libraries/{lib}/profile").json() == before
    assert admin.get(f"{API}/jobs").json()["total"] == 0
    assert out["reading"] is None  # the scan has finished

    too_many = {"profiles": {str(i): None for i in range(7)}}
    assert admin.post(f"{API}/libraries/{lib}/estimate", json=too_many).status_code == 422
    assert admin.post(f"{API}/libraries/999/estimate", json=body).status_code == 404


def test_estimate_reports_reading_progress_during_a_scan(
    app: FastAPI,  # noqa: F811
    settings: Settings,
) -> None:
    admin, lib, _path = setup(app, settings, FAST)
    # A scan part-way through reading (set directly: real scans of tiny files end at once).
    progress = ScanProgress(lib, phase="probing", probed=200, to_probe=3000, found_bytes=10**12)
    app.state.scanner._progress[lib] = progress
    body = {"profiles": {"balanced": {**FAST, "quality": 6}}}
    out = admin.post(f"{API}/libraries/{lib}/estimate", json=body).json()
    assert out["reading"] == {"probed": 200, "to_probe": 3000, "found_bytes": 10**12}
    progress.enter("languages")  # reading is over; only the language lookup remains
    assert admin.post(f"{API}/libraries/{lib}/estimate", json=body).json()["reading"] is None


def test_onboarding_state(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, _lib, _path = setup(app, settings, FAST)
    assert admin.get(f"{API}/onboarding").json() == {
        "wizard_seen": False,
        "server_steps_done": False,
    }
    saved = admin.put(f"{API}/onboarding", json={"wizard_seen": True, "server_steps_done": True})
    assert saved.status_code == 200
    assert admin.get(f"{API}/onboarding").json()["server_steps_done"] is True
    bad = admin.put(f"{API}/onboarding", json={"wizard_seen": True, "extra": 1})
    assert bad.status_code == 422
