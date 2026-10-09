"""Folder watcher (ADR-0025), rescanning only the folders that changed (ADR-0030)."""

import time
from collections.abc import Callable
from pathlib import Path

from reelhaven.db import Database, Library
from reelhaven.watcher import (
    Folders,
    FolderWatcher,
    WatchState,
    changed_folders,
    folder_times,
    relevant,
    title_folder,
)


def test_relevant_events() -> None:
    assert relevant("created", "/m/Film (2020)/film.mkv", False)
    assert relevant("moved", "/m/Film (2020)/film.MP4", False)
    assert relevant("closed", "/m/Film (2020)/film.mkv", False)  # finished writing
    assert relevant("deleted", "/m/Show/Season 1", True)  # a folder went away
    assert not relevant("modified", "/m/Film (2020)/film.mkv", False)  # mid-copy noise
    assert not relevant("created", "/m/Film (2020)/poster.jpg", False)
    assert not relevant("created", "/m/.reelhaven/work/1/film.mkv", False)  # our own files
    assert not relevant("closed", "/m/Show", True)


def test_title_folder() -> None:
    root = "/media/TV"
    assert title_folder(root, "/media/TV/Show/Season 1/e1.mkv", False) == "Show"
    assert title_folder(root, "/media/TV/Show/Season 2", True) == "Show"
    assert title_folder(root, "/media/TV/New Show", True) == "New Show"
    assert title_folder(root, "/media/TV/loose.mkv", False) is None  # can't be placed
    assert title_folder(root, "/media/TV", True) is None
    assert title_folder(root, "/elsewhere/x.mkv", False) is None


def test_watch_state_timeline() -> None:
    state = WatchState(settle_s=30, stable_s=120, poll_s=900)
    assert state.due({1}, now=0) == []
    state.changed(1, now=10, folder="Show A")
    assert state.due({1}, now=30) == []  # still settling (a season pack arriving)
    state.changed(1, now=35, folder="Show B")
    assert state.due({1}, now=60) == []
    assert state.due({1}, now=65) == [(1, frozenset({"Show A", "Show B"}))]
    state.started(1, now=65, folders=frozenset({"Show A", "Show B"}), after_change=True)
    assert state.due({1}, now=100) == []
    # The follow-up, once copies have settled, checks the same folders again.
    assert state.due({1}, now=200) == [(1, frozenset({"Show A", "Show B"}))]
    state.started(1, now=200, folders=frozenset({"Show A", "Show B"}), after_change=False)
    assert state.due({1}, now=1000) == []
    state.forget(1)
    assert state.due({1}, now=1100) == []


def test_a_change_that_cant_be_placed_rescans_everything() -> None:
    state = WatchState(settle_s=30, stable_s=120, poll_s=900)
    state.changed(1, now=0, folder="Show A")
    state.changed(1, now=1, folder=None)
    state.changed(1, now=2, folder="Show B")
    due: list[tuple[int, Folders]] = state.due({1}, now=40)
    assert due == [(1, None)]


def test_poll_timing() -> None:
    state = WatchState(settle_s=30, stable_s=120, poll_s=900)
    assert state.poll_due({1}, now=0) == [1]  # first sight: record the folder times
    state.polled(1, now=0)
    assert state.poll_due({1}, now=600) == []
    assert state.poll_due({1}, now=900) == [1]


def test_folder_times_find_the_changed_title_folders(tmp_path: Path) -> None:
    (tmp_path / "Show A" / "Season 1").mkdir(parents=True)
    (tmp_path / "Show B" / "Season 1").mkdir(parents=True)
    (tmp_path / ".reelhaven" / "work").mkdir(parents=True)
    before = folder_times(tmp_path)
    assert set(before) == {"", "Show A", "Show A/Season 1", "Show B", "Show B/Season 1"}

    time.sleep(0.01)
    (tmp_path / "Show A" / "Season 1" / "e2.mkv").write_bytes(b"x")  # new episode
    (tmp_path / "Show C").mkdir()  # new series
    (tmp_path / ".reelhaven" / "work" / "tmp.mkv").write_bytes(b"x")  # ours: ignored
    assert changed_folders(before, folder_times(tmp_path)) == {"Show A", "Show C"}

    (tmp_path / "Show B" / "Season 1").rmdir()
    (tmp_path / "Show B").rmdir()  # a series removed
    assert "Show B" in changed_folders(before, folder_times(tmp_path))


def wait_for(condition: Callable[[], bool], timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


def _library(db: Database, folder: Path, off: Path) -> int:
    with db.write() as session:
        library = Library(name="Movies", type="movies", path=str(folder), watch_mode="watch")
        session.add_all(
            [library, Library(name="Off", type="movies", path=str(off), watch_mode="off")]
        )
        session.flush()
        return library.id


def test_watcher_rescans_only_the_changed_folder(db: Database, tmp_path: Path) -> None:
    folder = tmp_path / "Movies"
    (folder / ".reelhaven" / "work").mkdir(parents=True)
    library_id = _library(db, folder, tmp_path / "Off")
    started: list[tuple[int, Folders]] = []

    def start_scan(library_id: int, folders: Folders) -> bool:
        started.append((library_id, folders))
        return True

    watcher = FolderWatcher(
        db, start_scan=start_scan, state=WatchState(settle_s=0.2, stable_s=600, poll_s=600)
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
            return bool(started)

        assert wait_for(scanned)
        assert started == [(library_id, frozenset({"Film (2020)"}))]

        with db.write() as session:
            row = session.get(Library, library_id)
            assert row is not None
            row.watch_mode = "off"
        assert watcher.reconcile() == []
    finally:
        watcher.stop()


def test_safety_net_rescans_folders_changed_behind_the_watchers_back(
    db: Database, tmp_path: Path
) -> None:
    folder = tmp_path / "Movies"
    (folder / "Film A").mkdir(parents=True)
    library_id = _library(db, folder, tmp_path / "Off")
    started: list[tuple[int, Folders]] = []
    clock = [0.0]

    class NoEvents:  # e.g. a change made directly on an Unraid disk
        def start(self) -> None: ...
        def stop(self) -> None: ...
        def schedule(self, *_args: object, **_kwargs: object) -> object:
            return object()

        def unschedule(self, _handle: object) -> None: ...

    def start_scan(library_id: int, folders: Folders) -> bool:
        started.append((library_id, folders))
        return True

    watcher = FolderWatcher(
        db,
        start_scan=start_scan,
        state=WatchState(settle_s=30, stable_s=600, poll_s=900),
        clock=lambda: clock[0],
        observer_factory=NoEvents,
    )
    watcher.tick()  # first check: only remembers the folder times
    assert started == []
    time.sleep(0.01)
    (folder / "Film B").mkdir()
    (folder / "Film B" / "film.mkv").write_bytes(b"x")
    clock[0] = 900.0
    watcher.tick()  # the check finds Film B; it settles first
    clock[0] = 931.0
    watcher.tick()
    assert started == [(library_id, frozenset({"Film B"}))]
