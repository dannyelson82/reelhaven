"""Find my sweet spot (ADR-0031): one scene encoded at several qualities, on the CPU."""

import hashlib
import os

import pytest
from fastapi import FastAPI

from reelhaven.config import Settings
from reelhaven.jobs.tune import KEEP_SESSIONS, estimate_size, scene_window, session_dir
from tests.helpers import API
from tests.media_fixtures import FFMPEG
from tests.test_encode_pipeline import (  # noqa: F401 - shared fixture
    FAST,
    app,
    file_id,
    setup,
)

pytestmark = pytest.mark.skipif(
    FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed"
)


def test_scene_window() -> None:
    assert scene_window(7200) == (2880.0, 30.0)  # 40 % in: past the opening, before credits
    assert scene_window(40) == (10.0, 30.0)  # never runs past the end
    assert scene_window(12) == (0.0, 12)  # a short video: all of it


def test_estimate_scales_only_the_video() -> None:
    # A 10 GB file whose video is 8 GB; the scene halved: 2 GB of audio + 4 GB of video.
    assert estimate_size(10_000, 8_000, 300, 150) == 6_000
    assert estimate_size(10_000, None, 300, 150) == 5_000  # video size unknown: whole file
    assert estimate_size(10_000, 8_000, 0, 150) == 10_000  # nothing to go on: unchanged


def test_sweet_spot_session(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, path = setup(app, settings, FAST)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    started = admin.post(
        f"{API}/tune-sessions", json={"file_id": file_id(admin, lib), "settings": FAST}
    )
    assert started.status_code == 201, started.text
    tune = started.json()
    assert tune["file"] == "Film (2020)/film.mkv" and tune["base"]["codec"] == "hevc"
    assert [s["quality"] for s in tune["steps"]] == [8, 6, 4]  # best quality first
    assert app.state.queue.wait_idle(300)

    tune = admin.get(f"{API}/tune-sessions/{tune['id']}").json()
    assert {s["status"] for s in tune["steps"]} == {"done"}, tune["steps"]
    results = [s["result"] for s in tune["steps"]]
    sizes = [r["bytes_after"] for r in results]
    assert sizes == sorted(sizes, reverse=True)  # smaller and smaller
    assert all(r["bytes_after"] < r["bytes_before"] for r in results)
    assert all(r["rating"] and r["frame_times"] and r["clip"] for r in results)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before  # original untouched

    # Dial in: a half step between two of them.
    added = admin.post(f"{API}/tune-sessions/{tune['id']}/steps", json={"quality": 6.5})
    assert added.status_code == 201, added.text
    assert [s["quality"] for s in added.json()["steps"]] == [8, 6.5, 6, 4]
    assert app.state.queue.wait_idle(300)
    step = next(s for s in admin.get(f"{API}/tune-sessions/{tune['id']}").json()["steps"]
                if s["quality"] == 6.5)  # fmt: skip
    assert step["status"] == "done"
    assert results[1]["bytes_after"] <= step["result"]["bytes_after"] <= results[0]["bytes_after"]
    again = admin.post(f"{API}/tune-sessions/{tune['id']}/steps", json={"quality": 6.5})
    assert again.status_code == 409 and again.json()["detail"] == "step_exists"
    bad = admin.post(f"{API}/tune-sessions/{tune['id']}/steps", json={"quality": 6.3})
    assert bad.status_code == 422

    # Stills and clips of each step, for the viewer and the players.
    frame = admin.get(f"{API}/tune-steps/{step['id']}/frames/0/encoded")
    assert frame.status_code == 200 and frame.headers["content-type"] == "image/webp"
    clip = admin.get(f"{API}/tune-steps/{step['id']}/clips/source")
    assert clip.status_code == 200 and clip.content[4:8] == b"ftyp"

    # The steps show on the Jobs page, but can't be retried from there.
    jobs = [j for j in admin.get(f"{API}/jobs").json()["items"] if j["type"] == "tune"]
    assert len(jobs) == 4 and jobs[0]["device"] == "cpu"
    assert admin.post(f"{API}/jobs/{jobs[0]['id']}/retry").status_code == 409

    # Deleting a session removes its files.
    folder = session_dir(app.state.settings, tune["id"])
    assert folder.is_dir()
    assert admin.delete(f"{API}/tune-sessions/{tune['id']}").status_code == 204
    assert not folder.exists()
    assert admin.get(f"{API}/tune-sessions/{tune['id']}").status_code == 404


def test_only_the_latest_sessions_are_kept(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, _path = setup(app, settings, FAST)
    body = {"file_id": file_id(admin, lib), "settings": FAST}
    ids = []
    for _ in range(KEEP_SESSIONS + 1):
        ids.append(admin.post(f"{API}/tune-sessions", json=body).json()["id"])
        assert app.state.queue.wait_idle(300)
    kept = [t["id"] for t in admin.get(f"{API}/tune-sessions").json()]
    assert kept == list(reversed(ids[1:]))  # the oldest went, files and all
    assert not session_dir(app.state.settings, ids[0]).exists()


def test_start_needs_a_readable_file(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, _lib, _path = setup(app, settings, FAST)
    missing = admin.post(f"{API}/tune-sessions", json={"file_id": 999, "settings": FAST})
    assert missing.status_code == 404
