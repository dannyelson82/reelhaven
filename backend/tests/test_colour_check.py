"""Colour check (ADR-0036) and swapping damaged / wrong-colour files (ADR-0035)."""

import os
import subprocess
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import update

from reelhaven.automation import pick_wrong_language, swap_cause
from reelhaven.colour_check import (
    Sample,
    frame_sample,
    is_candidate,
    measure,
    result,
    verdict,
)
from reelhaven.config import Settings
from reelhaven.db import Database, MediaFile
from reelhaven.dryrun import plan_library
from reelhaven.media.info import MediaInfo, Stream
from reelhaven.media.probe import probe
from tests.helpers import API
from tests.media_fixtures import FFMPEG
from tests.test_remux import MULTI, app, setup_library  # noqa: F401 - fixture

needs_ffmpeg = pytest.mark.skipif(
    FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed"
)


def video(**kw: object) -> MediaInfo:
    stream = Stream(index=0, kind="video", codec="hevc", **kw)  # type: ignore[arg-type]
    return MediaInfo(
        container="matroska", duration_s=60, size_bytes=1, bit_rate=1, streams=[stream]
    )


def test_candidates_are_untagged_10_bit_sdr_without_dolby_vision() -> None:
    assert is_candidate(video(bit_depth=10, hdr="sdr"))
    assert is_candidate(video(bit_depth=10, hdr="sdr", color_transfer="unknown"))
    assert not is_candidate(video(bit_depth=8, hdr="sdr"))
    assert not is_candidate(video(bit_depth=10, hdr="hdr10"))
    assert not is_candidate(video(bit_depth=10, hdr="sdr", color_transfer="bt709"))
    assert not is_candidate(video(bit_depth=10, hdr="dolby_vision", dv_profile=5))


def test_frame_sample_counts_green_and_magenta_and_skips_darkness() -> None:
    green, magenta, grey, black = (
        bytes([40, 200, 60]),
        bytes([200, 60, 190]),
        bytes([120] * 3),
        bytes(3),
    )
    sample = frame_sample(green * 3 + magenta + grey * 4 + black * 10)
    assert sample == Sample(green=3 / 8, magenta=1 / 8)
    assert frame_sample(black * 10) is None


def test_verdict_needs_a_cast_through_most_of_the_file() -> None:
    # The owner's damaged episode: about a third green, half of the frames.
    e02 = [
        Sample(g, 0.0) for g in (0.06, 0, 0.43, 0.93, 0.01, 0.1, 0.69, 0.26, 0.78, 0.12, 0.64, 0)
    ]
    assert verdict(e02) == "wrong_colours"
    one_green_scene = [Sample(0.4, 0)] + [Sample(0.0, 0)] * 11
    assert verdict(one_green_scene) == "ok"
    assert verdict([Sample(1.0, 0)] * 3) == "ok"  # too few frames to judge
    assert result(e02, "1:2")["green_frames"] == 6


def clip(path: Path, tint: bool) -> Path:
    """A 10-bit clip with no colour tags; ``tint`` makes it green like a lost Dolby
    Vision profile 5 picture."""
    mix = "colorchannelmixer=rr=0.4:gg=1.0:bb=0.4," if tint else ""
    args = [
        FFMPEG or "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10:duration=13",
        "-f", "lavfi", "-i", "sine=duration=13",
        "-vf", f"{mix}format=yuv420p10le", "-c:v", "ffv1", "-g", "5",
        "-c:a", "aac", str(path),
    ]  # fmt: skip
    subprocess.run(args, check=True)  # noqa: S603 - argument list, no shell
    return path


@needs_ffmpeg
def test_measure_tells_a_green_picture_from_a_normal_one(tmp_path: Path) -> None:
    for tint, expected in ((True, "wrong_colours"), (False, "ok")):
        path = clip(tmp_path / f"{tint}.mkv", tint)
        info = probe(path)
        assert is_candidate(info)
        samples = measure(FFMPEG or "ffmpeg", path, info.duration_s or 0)
        assert len(samples) >= 10
        assert verdict(samples) == expected


@needs_ffmpeg
def test_wrong_colours_and_damaged_files_are_swapped(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, root = setup_library(app, settings, {"Good (2020)/good.mkv": MULTI})
    app.state.queue.stop()
    app.state.automation.stop()
    (root / "Green (2021)").mkdir()
    green = clip(root / "Green (2021)" / "green.mkv", True)
    broken = root / "Broken (2022)" / "broken.mkv"
    broken.parent.mkdir()
    broken.write_bytes(b"\0" * 4096)  # starts with zeros, like the owner's damaged files
    two_days_ago = time.time() - 2 * 86400
    for path in (green, broken):
        os.utime(path, (two_days_ago, two_days_ago))
    admin.post(f"{API}/libraries/{lib}/scan")
    app.state.scanner.wait(lib, timeout=60)
    for title in admin.get(f"{API}/libraries/{lib}/titles").json()["items"]:
        admin.put(f"{API}/titles/{title['id']}/language", json={"language": "eng"})

    app.state.colour_check.run_pass()
    plans = {p.relative_path: p for p in plan_library(app.state.db, lib)}
    assert swap_cause(plans["Green (2021)/green.mkv"]) == "wrong_colours"
    assert swap_cause(plans["Good (2020)/good.mkv"]) is None
    # Unreadable, but its time says it was written long ago: damaged, not still copying.
    assert swap_cause(plans["Broken (2022)/broken.mkv"]) == "damaged"
    green_plan = plans["Green (2021)/green.mkv"].plan
    assert green_plan is not None and green_plan.action == "skip"

    review = admin.get(f"{API}/review", params={"kind": "wrong_colours"}).json()
    assert [i["relative_path"] for i in review["items"]] == ["Green (2021)/green.mkv"]
    assert "Green and purple picture" in review["items"][0]["detail"]

    chosen = pick_wrong_language(plans.values(), active=set(), gave_up={}, current={}, limit=10)
    assert sorted(p.relative_path for p in chosen) == [
        "Broken (2022)/broken.mkv",
        "Green (2021)/green.mkv",
    ]

    # A file that only just arrived and can't be read yet may still be copying.
    db: Database = app.state.db
    with db.write() as session:
        session.execute(
            update(MediaFile)
            .where(MediaFile.relative_path == "Broken (2022)/broken.mkv")
            .values(mtime_ns=time.time_ns())
        )
    plans = {p.relative_path: p for p in plan_library(db, lib)}
    assert swap_cause(plans["Broken (2022)/broken.mkv"]) is None

    # Moving the green file aside asks for another copy, with the reason in the job.
    response = admin.post(
        f"{API}/files/{plans['Green (2021)/green.mkv'].file_id}/wrong-language",
        json={"action": "quarantine"},
    )
    assert response.status_code == 201, response.text
    job = admin.get(f"{API}/jobs/{response.json()['job_id']}").json()
    assert job["summary"] == "Quarantine: wrong colours"
