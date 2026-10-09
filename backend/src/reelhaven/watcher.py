"""Folder watcher (ADR-0025): rescan a library soon after its files change.

inotify (via watchdog) notices changes within seconds; Unraid user shares can
miss events for changes made directly on a disk, so every ``POLL_S`` the
folders' modification times are also compared with the last check. Either way
only the top-level folders that changed are rescanned (ADR-0030). The watcher
only decides *when* and *where* to rescan: the scanner skips unchanged files
and leaves files that are still being copied for the next scan, which is why
one follow-up scan of the same folders runs after the stability time.
"""

import logging
import os
import threading
import time
from collections.abc import Callable, Iterable
from functools import partial
from pathlib import Path, PurePath
from typing import Any

from sqlalchemy import select
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from reelhaven.db import Database, Library
from reelhaven.paths import INTERNAL_DIR
from reelhaven.scanner import VIDEO_EXTENSIONS

logger = logging.getLogger(__name__)

SETTLE_S = 30.0  # wait for a burst of events (a season pack) to finish
STABLE_S = 120.0  # the scanner's "still being copied" time (ARCHITECTURE.md §6.10)
POLL_S = 15 * 60.0
TICK_S = 5.0
_EVENTS = ("created", "deleted", "moved", "closed")


def relevant(event_type: str, path: str, is_directory: bool) -> bool:
    """Whether a file-system event can change what's in the library."""
    if event_type not in _EVENTS or INTERNAL_DIR in PurePath(path).parts:
        return False
    if is_directory:
        return event_type != "closed"  # a folder copied in, renamed or removed
    return PurePath(path).suffix.lower() in VIDEO_EXTENSIONS


Folders = frozenset[str] | None  # top-level folders to rescan; None: the whole library


def title_folder(root: str, path: str, is_directory: bool) -> str | None:
    """The top-level folder under ``root`` a change happened in (ADR-0030); None when it
    can't be placed in one (the root itself, or a file directly in the root)."""
    try:
        parts = PurePath(path).relative_to(root).parts
    except ValueError:
        return None
    if not parts or (len(parts) == 1 and not is_directory):
        return None
    return parts[0]


def _merge(current: set[str] | None, more: Iterable[str] | None) -> set[str] | None:
    if current is None or more is None:
        return None
    return current | set(more)


def folder_times(root: Path) -> dict[str, int]:
    """Every folder under ``root`` (relative path) and its modification time. Adding,
    removing or renaming a file changes its folder's time; files aren't touched."""
    times: dict[str, int] = {}
    stack = [(root, "")]
    while stack:
        path, relative = stack.pop()
        try:
            mtime = path.stat().st_mtime_ns
            entries = list(os.scandir(path))
        except OSError:
            continue
        times[relative] = mtime
        for entry in entries:
            if entry.name.startswith(".") or entry.name == INTERNAL_DIR:
                continue
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                stack.append(
                    (Path(entry.path), f"{relative}/{entry.name}" if relative else entry.name)
                )
    return times


def changed_folders(before: dict[str, int], after: dict[str, int]) -> set[str]:
    """Top-level folders with a folder added, removed or modified between two checks.
    The root's own time is ignored: new and removed top-level folders show up themselves."""
    return {
        relative.split("/")[0]
        for relative in set(before) | set(after)
        if relative and before.get(relative) != after.get(relative)
    }


class WatchState:
    """When each library is due for a (partial) rescan. Pure: the clock is passed in."""

    def __init__(
        self, settle_s: float = SETTLE_S, stable_s: float = STABLE_S, poll_s: float = POLL_S
    ):
        self._settle, self._stable, self._poll = settle_s, stable_s, poll_s
        self._changed: dict[int, float] = {}  # last event per library
        self._folders: dict[int, set[str] | None] = {}  # where those events happened
        self._follow_up: dict[int, tuple[float, Folders]] = {}
        self._last_poll: dict[int, float] = {}

    def changed(self, library_id: int, now: float, folder: str | None = None) -> None:
        self._changed[library_id] = now
        current = self._folders.get(library_id, set())
        self._folders[library_id] = _merge(current, None if folder is None else [folder])

    def due(self, watched: set[int], now: float) -> list[tuple[int, Folders]]:
        """Libraries to rescan now, each with the folders to rescan."""
        due: list[tuple[int, Folders]] = []
        for library_id in sorted(watched):
            changed = self._changed.get(library_id)
            follow_up = self._follow_up.get(library_id)
            folders: set[str] | None = set()
            hit = False
            if changed is not None and now - changed >= self._settle:
                folders, hit = _merge(folders, self._folders.get(library_id, set())), True
            if follow_up is not None and now >= follow_up[0]:
                folders, hit = _merge(folders, follow_up[1]), True
            if hit:
                due.append((library_id, None if folders is None else frozenset(folders)))
        return due

    def poll_due(self, watched: set[int], now: float) -> list[int]:
        """Libraries whose folder times should be checked (first sight: right away, which
        only records them)."""
        return [
            library_id
            for library_id in sorted(watched)
            if now - self._last_poll.setdefault(library_id, now - self._poll) >= self._poll
        ]

    def polled(self, library_id: int, now: float) -> None:
        self._last_poll[library_id] = now

    def started(self, library_id: int, now: float, folders: Folders, after_change: bool) -> None:
        """A scan started. After a change, check the same folders again once copies have
        settled."""
        self._follow_up.pop(library_id, None)
        self._folders.pop(library_id, None)
        if self._changed.pop(library_id, None) is not None and after_change:
            self._follow_up[library_id] = (now + self._stable + 15, folders)

    def pending_change(self, library_id: int) -> bool:
        return library_id in self._changed

    def forget(self, library_id: int) -> None:
        for table in (self._changed, self._folders, self._follow_up, self._last_poll):
            table.pop(library_id, None)


class _Handler(FileSystemEventHandler):
    def __init__(self, root: str, on_change: Callable[[str | None], None]) -> None:
        self._root = root
        self._on_change = on_change

    def on_any_event(self, event: FileSystemEvent) -> None:
        paths = [str(p) for p in (event.src_path, getattr(event, "dest_path", "") or "") if p]
        for path in paths:
            if relevant(event.event_type, path, event.is_directory):
                self._on_change(title_folder(self._root, path, event.is_directory))


class FolderWatcher:
    def __init__(
        self,
        db: Database,
        start_scan: Callable[[int, Folders], bool],
        state: WatchState | None = None,
        clock: Callable[[], float] = time.monotonic,
        observer_factory: Callable[[], Any] = Observer,
    ) -> None:
        self._db = db
        self._start_scan = start_scan
        self._state = state or WatchState()
        self._clock = clock
        self._lock = threading.Lock()
        self._observer = observer_factory()
        self._watches: dict[int, tuple[str, Any]] = {}  # library -> (path, watch handle)
        self._folder_times: dict[int, dict[str, int]] = {}  # the last safety-net check
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._observer.start()
        self._thread = threading.Thread(target=self._loop, name="folder-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(5)
        self._observer.stop()

    def _loop(self) -> None:
        while not self._stop.wait(TICK_S):
            try:
                self.tick()
            except Exception:
                logger.exception("folder watcher tick failed")

    def tick(self) -> None:
        watched = self.reconcile()
        now = self._clock()
        with self._lock:
            polls = self._state.poll_due(set(watched), now)
        for library_id in polls:
            self._check_folders(library_id, now)
        with self._lock:
            due = self._state.due(set(watched), now)
        for library_id, folders in due:
            with self._lock:
                after_change = self._state.pending_change(library_id)
            # False: a scan is already running; it's retried on the next tick.
            if self._start_scan(library_id, folders):
                with self._lock:
                    self._state.started(library_id, now, folders, after_change)

    def _check_folders(self, library_id: int, now: float) -> None:
        """The safety net for missed events: compare folder times with the last check and
        mark the title folders that changed (ADR-0030)."""
        with self._lock:
            self._state.polled(library_id, now)
        path = self._watches.get(library_id, ("", None))[0]
        if not path:
            return
        after = folder_times(Path(path))
        before = self._folder_times.get(library_id)
        self._folder_times[library_id] = after
        if before is None:
            return  # first check since start: only remember the times
        for folder in sorted(changed_folders(before, after)):
            self.changed(library_id, folder)

    def reconcile(self) -> list[int]:
        """Watch exactly the libraries that are not Off; returns their ids."""
        with self._db.read() as session:
            wanted = {
                lib.id: lib.path
                for lib in session.scalars(select(Library).where(Library.watch_mode != "off"))
            }
        for library_id, (path, handle) in list(self._watches.items()):
            if wanted.get(library_id) != path:
                self._observer.unschedule(handle)
                del self._watches[library_id]
                self._folder_times.pop(library_id, None)
                with self._lock:
                    self._state.forget(library_id)
        for library_id, path in wanted.items():
            if library_id in self._watches:
                continue
            try:
                handle = self._observer.schedule(
                    _Handler(path, partial(self.changed, library_id)), path, recursive=True
                )
            except OSError as exc:  # e.g. too many folders for inotify: polling still works
                logger.warning(
                    "can't watch a library folder; it is rescanned every 15 minutes instead",
                    extra={"library_id": library_id, "error": str(exc)},
                )
                handle = None
            self._watches[library_id] = (path, handle)
        return list(wanted)

    def changed(self, library_id: int, folder: str | None = None) -> None:
        """Files in this library changed (inotify, a Sonarr/Radarr webhook or the folder
        check), in ``folder`` (top-level), or somewhere unknown (None: rescan it all)."""
        with self._lock:
            self._state.changed(library_id, self._clock(), folder)
