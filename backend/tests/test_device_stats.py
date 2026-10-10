"""Per-device performance and throughput (ADR-0032)."""

import os
from dataclasses import replace
from datetime import date, datetime

import pytest
from fastapi import FastAPI

from reelhaven.config import Settings
from reelhaven.device_stats import JobRow, daily, device_stats
from tests.helpers import API
from tests.media_fixtures import FFMPEG
from tests.test_encode_pipeline import FAST, app, file_id, setup  # noqa: F401 - shared fixture


def at(month: int, day: int) -> datetime:
    return datetime(2026, month, day, 12, 0)  # noqa: DTZ001 - local wall-clock time


ENCODE = JobRow(
    finished=at(10, 8),
    type="encode",
    status="done",
    device="nvidia:0",
    decoder="gpu",
    outcome="replaced",
    saved=4_000,
    video_seconds=7200,
    work_seconds=1800,
    fps=96,
)


def test_device_stats() -> None:
    rows = [
        ENCODE,
        replace(
            ENCODE,
            video_seconds=3600,
            work_seconds=1800,
            fps=48,
            decoder="cpu",
            saved=0,
            outcome="no_gain",
        ),
        replace(ENCODE, status="failed", outcome=None),
        replace(ENCODE, device="intel:0", fps=60),
        replace(ENCODE, type="remux", device=None),  # track changes use no device
        replace(ENCODE, finished=at(8, 1)),  # outside the window
    ]
    stats = device_stats(rows, since=at(9, 9))
    nvidia, intel = stats
    assert (nvidia.device, nvidia.files, nvidia.failed, nvidia.saved) == ("nvidia:0", 2, 1, 4_000)
    assert (nvidia.video_hours, nvidia.work_hours, nvidia.speed) == (3.0, 1.0, 3.0)
    assert nvidia.fps == 80.0  # weighted by video length: (96*2h + 48*1h) / 3h
    assert nvidia.gpu_decoded == 0.5
    assert intel.files == 1
    assert len(device_stats(rows)[0:1]) == 1 and device_stats(rows)[0].files == 3  # all time


def test_daily() -> None:
    rows = [
        ENCODE,
        replace(ENCODE, type="remux", saved=10),
        replace(ENCODE, status="failed", outcome=None),
        replace(ENCODE, finished=at(10, 1)),
        replace(ENCODE, finished=at(1, 1)),  # too old
    ]
    days = daily(rows, date(2026, 10, 9), days=10)
    assert (
        len(days) == 10 and days[0].day == date(2026, 9, 30) and days[-1].day == date(2026, 10, 9)
    )
    by_day = {d.day: d for d in days}
    assert (by_day[date(2026, 10, 8)].encoded, by_day[date(2026, 10, 8)].remuxed) == (1, 1)
    assert by_day[date(2026, 10, 8)].failed == 1 and by_day[date(2026, 10, 8)].saved == 4_010
    assert by_day[date(2026, 10, 1)].encoded == 1
    assert by_day[date(2026, 10, 9)].encoded == 0


@pytest.mark.skipif(FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed")
def test_performance_api(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, _path = setup(app, settings, FAST)
    empty = admin.get(f"{API}/stats/performance").json()
    assert empty["devices"] == [] and len(empty["daily"]) == 30
    assert admin.post(f"{API}/files/{file_id(admin, lib)}/apply").status_code == 201
    assert app.state.queue.wait_idle(180)
    data = admin.get(f"{API}/stats/performance", params={"days": 0}).json()
    (cpu,) = data["devices"]
    assert (cpu["device"], cpu["files"], cpu["failed"]) == ("cpu", 1, 0)
    assert cpu["saved"] > 0 and cpu["fps"] > 0 and cpu["gpu_decoded"] == 0  # a CPU encode
    assert data["daily"][-1]["encoded"] == 1
