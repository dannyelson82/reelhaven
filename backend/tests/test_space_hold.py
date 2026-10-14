"""Stopping all work while a disk is full, and carrying on once there's room."""

import errno
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from reelhaven import space_hold
from reelhaven.config import Settings
from reelhaven.db import AuditLog, Database
from reelhaven.jobs import queue as queue_module
from reelhaven.jobs.pipeline import JobFailedError, process
from reelhaven.jobs.runner import RunError
from reelhaven.space_hold import SpaceHold, has_room, is_out_of_space, merged, needed_for
from tests.helpers import API
from tests.test_remux import MULTI, app, jobs, setup_library  # noqa: F401 - shared fixture

FULL = "[Errno 28] No space left on device: '/media/Movies/.reelhaven/work/1/film.mkv'"


# --- pure parts --------------------------------------------------------------------------


def test_out_of_space_is_recognised() -> None:
    assert is_out_of_space(OSError(errno.ENOSPC, "No space left on device"))
    assert is_out_of_space(OSError(errno.EDQUOT, "Disk quota exceeded"))
    # ffmpeg's own words, wrapped the way the pipelines wrap them.
    try:
        try:
            raise RunError("av_interleaved_write_frame(): No space left on device")
        except RunError as inner:
            raise JobFailedError(str(inner)) from inner
    except JobFailedError as exc:
        assert is_out_of_space(exc)
    # Only the cause says so.
    try:
        try:
            raise OSError(errno.ENOSPC, "x")
        except OSError as inner:
            raise JobFailedError("could not copy the result") from inner
    except JobFailedError as exc:
        assert is_out_of_space(exc)
    assert not is_out_of_space(JobFailedError("the original file changed since it was planned"))
    assert not is_out_of_space(OSError(errno.EACCES, "Permission denied"))


def test_room_and_merging() -> None:
    gib = 1024**3
    assert needed_for(10 * gib) == 12 * gib
    assert needed_for(None) == 2 * gib
    assert has_room({"/media/tv": 20 * gib, "/transcode": 13 * gib}, 12 * gib)
    assert not has_room({"/media/tv": 20 * gib, "/transcode": 11 * gib}, 12 * gib)
    first = SpaceHold(
        since=datetime(2026, 10, 14, tzinfo=UTC), paths=["/transcode", "/media/tv"],
        needed_bytes=5, error="full",
    )  # fmt: skip
    second = SpaceHold(
        since=datetime(2026, 10, 15, tzinfo=UTC), paths=["/transcode", "/media/films"],
        needed_bytes=9, error="also full",
    )  # fmt: skip
    both = merged(first, second)
    assert both.paths == ["/media/films", "/media/tv", "/transcode"]
    assert (both.needed_bytes, both.error, both.since) == (9, "full", first.since)
    assert merged(None, second) == second


def test_free_space_of_a_missing_folder_is_its_parent(tmp_path: Path) -> None:
    free = space_hold.free_space([str(tmp_path / "not" / "yet")])
    assert free[str(tmp_path / "not" / "yet")] > 0


# --- the queue ---------------------------------------------------------------------------


def test_full_disk_holds_everything_until_there_is_room(
    app: FastAPI,  # noqa: F811
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin, lib, _root = setup_library(
        app, settings, {"A (2020)/a.mkv": MULTI, "B (2021)/b.mkv": MULTI}
    )
    real_process = process
    calls: list[int] = []

    def fill_disk_once(db: Database, cfg: Settings, job_id: int) -> None:
        calls.append(job_id)
        if len(calls) == 1:
            raise JobFailedError(FULL) from OSError(errno.ENOSPC, "No space left on device")
        real_process(db, cfg, job_id)

    disks: dict[str, Any] = {"free": 0}
    monkeypatch.setattr(queue_module, "process", fill_disk_once)
    monkeypatch.setattr(space_hold, "free_space", lambda paths: {p: disks["free"] for p in paths})
    # One track-change job at a time, so the second file is still waiting when the first fails.
    app.state.queue.stop()
    app.state.queue = type(app.state.queue)(app.state.db, settings, workers=1)
    app.state.queue.start()

    count = admin.get(f"{API}/libraries/{lib}/dry-run").json()["remux"]
    admin.post(f"{API}/libraries/{lib}/apply", json={"expected_count": count})
    assert app.state.queue.wait_idle(60)

    # The failed job is back in the queue, nothing else started, and the UI can say why.
    assert len(calls) == 1
    assert sorted(j["status"] for j in jobs(admin)) == ["queued", "queued"]
    hold = admin.get(f"{API}/automation/space-hold").json()
    assert hold["error"] == FULL
    assert {d["path"] for d in hold["disks"]} == {
        str(settings.transcode_dir),
        str(settings.media_root / "Movies"),
    }
    assert hold["needed_bytes"] > 2 * 1024**3

    # Still full: checking again changes nothing.
    assert admin.post(f"{API}/automation/space-hold/check").json() is not None
    assert app.state.queue.wait_idle(5)
    assert len(calls) == 1

    # Room again: the next check lifts the hold and both files are done.
    disks["free"] = 10**15
    assert admin.post(f"{API}/automation/space-hold/check").json() is None
    assert app.state.queue.wait_idle(120)
    assert sorted(j["status"] for j in jobs(admin)) == ["done", "done"]
    with app.state.db.read() as session:
        actions = session.scalars(select(AuditLog.action)).all()
    assert "queue.disk_full" in actions and "queue.disk_space_free" in actions


def test_resume_anyway(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, _lib, _root = setup_library(app, settings, {"A (2020)/a.mkv": MULTI})
    with app.state.db.write() as session:
        space_hold.save(
            session,
            SpaceHold(
                since=datetime(2026, 10, 14, tzinfo=UTC),
                paths=["/nowhere"],
                needed_bytes=10**18,
                error=FULL,
            ),
        )
    disks = admin.get(f"{API}/automation/space-hold").json()["disks"]
    assert [d["path"] for d in disks] == ["/nowhere"]
    assert app.state.queue.space_held(check_now=True)  # far too little room
    assert admin.delete(f"{API}/automation/space-hold").status_code == 204
    assert admin.get(f"{API}/automation/space-hold").json() is None
    assert admin.delete(f"{API}/automation/space-hold").status_code == 204  # already gone
