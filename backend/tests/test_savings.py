import os
from datetime import date, datetime

import pytest
from fastapi import FastAPI

from reelhaven.config import Settings
from reelhaven.savings import Event, month_start, summarise, week_start
from tests.helpers import API
from tests.media_fixtures import FFMPEG
from tests.test_encode_pipeline import FAST, app, file_id, setup  # noqa: F401 - shared fixture

needs_ffmpeg = pytest.mark.skipif(
    FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed"
)

GB = 1_000_000_000


def at(month: int, day: int) -> datetime:
    return datetime(2026, month, day, 12, 0)  # noqa: DTZ001 - local wall-clock time


def test_week_and_month_starts() -> None:
    assert week_start(date(2026, 10, 8)) == date(2026, 10, 5)  # a Thursday -> Monday
    assert week_start(date(2026, 10, 5)) == date(2026, 10, 5)
    assert month_start(date(2026, 10, 31)) == date(2026, 10, 1)


def test_summary() -> None:
    events = [
        Event(at(10, 6), 1, 4 * GB, 1),  # this week
        Event(at(10, 1), 1, 2 * GB, 1),  # last week, this month
        Event(at(9, 20), 2, 10 * GB, 1),  # last month
        Event(at(10, 7), 2, -3 * GB, -1),  # a restore this week gives space back
        Event(at(1, 3), 1, 1 * GB, 1),  # ten months ago: in the total and the monthly chart
        Event(at(1, 1).replace(year=2025), 1, 5 * GB, 1),  # too old for the charts
    ]
    s = summarise(events, at(10, 8))
    assert s.total_saved == 19 * GB and s.files == 4
    assert s.this_week == 1 * GB  # 4 saved - 3 restored
    assert s.this_month == 3 * GB
    assert len(s.weekly) == len(s.monthly) == 12
    assert s.weekly[-1].start == date(2026, 10, 5) and s.weekly[0].start == date(2026, 7, 20)
    assert [p.saved for p in s.weekly[-2:]] == [2 * GB, 1 * GB]
    assert s.monthly[-1].start == date(2026, 10, 1) and s.monthly[0].start == date(2025, 11, 1)
    assert s.monthly[-2].saved == 10 * GB and s.monthly[2].saved == 1 * GB  # Jan 2026
    assert [(lib.library_id, lib.saved, lib.files) for lib in s.libraries] == [
        (1, 12 * GB, 4),
        (2, 7 * GB, 0),
    ]


def test_nothing_yet() -> None:
    s = summarise([], at(10, 8))
    assert (s.total_saved, s.files, s.this_week, s.this_month, s.libraries) == (0, 0, 0, 0, [])
    assert all(p.saved == 0 for p in s.weekly + s.monthly)


@needs_ffmpeg
def test_savings_api_follows_jobs_and_restores(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, path = setup(app, settings, FAST)
    assert admin.get(f"{API}/stats/savings").json()["total_saved"] == 0
    before = path.stat().st_size
    assert admin.post(f"{API}/files/{file_id(admin, lib)}/apply").status_code == 201
    assert app.state.queue.wait_idle(180)
    saved = before - path.stat().st_size
    s = admin.get(f"{API}/stats/savings").json()
    assert (s["total_saved"], s["files"], s["this_week"], s["this_month"]) == (
        saved,
        1,
        saved,
        saved,
    )
    assert s["weekly"][-1]["saved"] == saved and len(s["monthly"]) == 12
    assert s["libraries"] == [{"library_id": lib, "name": "Movies", "saved": saved, "files": 1}]

    # Restoring the original gives the space back...
    original = admin.get(f"{API}/recycle").json()[0]
    assert admin.post(f"{API}/recycle/{original['id']}/restore").status_code == 200
    s = admin.get(f"{API}/stats/savings").json()
    assert (s["total_saved"], s["files"]) == (0, 0)
    # ...and restoring ReelHaven's version saves it again.
    swap = next(i for i in admin.get(f"{API}/recycle").json() if i["reason"] == "restore-swap")
    assert admin.post(f"{API}/recycle/{swap['id']}/restore").status_code == 200
    s = admin.get(f"{API}/stats/savings").json()
    assert (s["total_saved"], s["files"]) == (saved, 1)
