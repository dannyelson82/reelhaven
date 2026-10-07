"""Folder watcher (ADR-0025)."""

import time
from collections.abc import Callable
from pathlib import Path

from reelhaven.db import Database, Library
from reelhaven.watcher import FolderWatcher, WatchState, relevant


def test_relevant_events() -> None:
    assert relevant("created", "/m/Film (2020)/film.mkv", False)
    assert relevant("moved", "/m/Film (2020)/film.MP4", False)
    assert relevant("closed", "/m/Film (2020)/film.mkv", False)  # finished writing
    assert relevant("deleted", "/m/Show/Season 1", True)  # a folder went away
    assert not relevant("modified", "/m/Film (2020)/film.mkv", False)  # mid-copy noise
    assert not relevant("created", "/m/Film (2020)/poster.jpg", False)
    assert not relevant("created", "/m/.reelhaven/work/1/film.mkv", False)  # our own files
    assert not relevant("closed", "/m/Show", True)


def test_watch_state_timeline() -> None:
    state = WatchState(settle_s=30, stable_s=120, poll_s=900)
    assert state.due({1}, now=0) == []  # first sight: no immediate scan
    state.changed(1, now=10)
    assert state.due({1}, now=30) == []  # still settling (a season pack arriving)
    state.changed(1, now=35)
    assert state.due({1}, now=60) == []
    assert state.due({1}, now=65) == [1]
    state.started(1, now=65, after_change=True)
    assert state.due({1}, now=100) == []
    assert state.due({1}, now=200) == [1]  # follow-up once copies have settled
    state.started(1, now=200, after_change=False)
    assert state.due({1}, now=1000) == []
    assert state.due({1}, now=1100) == [1]  # periodic poll catches missed events
    state.forget(1)
    assert state.due({1}, now=1100) == []


def wait_for(condition: Callable[[], bool], timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


def test_watcher_rescans_after_a_real_change(db: Database, tmp_path: Path) -> None:
    folder = tmp_path / "Movies"
    (folder / ".reelhaven" / "work").mkdir(parents=True)
    with db.write() as session:
        library = Library(name="Movies", type="movies", path=str(folder), watch_mode="watch")
        off = Library(name="Off", type="movies", path=str(tmp_path / "Off"), watch_mode="off")
        session.add_all([library, off])
        session.flush()
        library_id = library.id
    started: list[int] = []

    def start_scan(library_id: int) -> bool:
        started.append(library_id)
        return True

    watcher = FolderWatcher(
        db,
        start_scan=start_scan,
        state=WatchState(settle_s=0.2, stable_s=600, poll_s=600),
    )
    watcher.start()
    try:
        assert watcher.reconcile() == [library_id]  # Off libraries aren't watched
        (folder / ".reelhaven" / "work" / "tmp.mkv").write_bytes(b"x")  # ours: ignored
        time.sleep(0.5)
        watcher.tick()
        assert started == []

        (folder / "Film (2020)").mkdir()
        (folder / "Film (2020)" / "film.mkv").write_bytes(b"x" * 100)

        def scanned() -> bool:
            watcher.tick()
            return started == [library_id]

        assert wait_for(scanned)

        with db.write() as session:
            row = session.get(Library, library_id)
            assert row is not None
            row.watch_mode = "off"
        assert watcher.reconcile() == []
    finally:
        watcher.stop()
