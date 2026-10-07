"""Folder watcher (ADR-0025): rescan a library soon after its files change.

inotify (via watchdog) notices changes within seconds; Unraid user shares can
miss events for changes made directly on a disk, so every watched library is
also rescanned every ``POLL_S``. The watcher only decides *when* to rescan: the
scanner skips unchanged files and leaves files that are still being copied for
the next scan, which is why one follow-up scan runs after the stability time.
"""

import logging
import threading
import time
from collections.abc import Callable
from functools import partial
from pathlib import PurePath
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


class WatchState:
    """When each library is due for a rescan. Pure: the clock is passed in."""

    def __init__(
        self, settle_s: float = SETTLE_S, stable_s: float = STABLE_S, poll_s: float = POLL_S
    ):
        self._settle, self._stable, self._poll = settle_s, stable_s, poll_s
        self._changed: dict[int, float] = {}  # last event per library
        self._follow_up: dict[int, float] = {}
        self._last_scan: dict[int, float] = {}

    def changed(self, library_id: int, now: float) -> None:
        self._changed[library_id] = now

    def due(self, watched: set[int], now: float) -> list[int]:
        due: list[int] = []
        for library_id in sorted(watched):
            changed = self._changed.get(library_id)
            follow_up = self._follow_up.get(library_id)
            last = self._last_scan.setdefault(library_id, now)  # first sight: poll later
            settled = changed is not None and now - changed >= self._settle
            follow_up_due = follow_up is not None and now >= follow_up
            if settled or follow_up_due or now - last >= self._poll:
                due.append(library_id)
        return due

    def started(self, library_id: int, now: float, after_change: bool) -> None:
        """A scan started. After a change, check again once copies have settled."""
        self._last_scan[library_id] = now
        self._follow_up.pop(library_id, None)
        if self._changed.pop(library_id, None) is not None and after_change:
            self._follow_up[library_id] = now + self._stable + 15

    def pending_change(self, library_id: int) -> bool:
        return library_id in self._changed

    def forget(self, library_id: int) -> None:
        for table in (self._changed, self._follow_up, self._last_scan):
            table.pop(library_id, None)


class _Handler(FileSystemEventHandler):
    def __init__(self, on_change: Callable[[], None]) -> None:
        self._on_change = on_change

    def on_any_event(self, event: FileSystemEvent) -> None:
        paths = [event.src_path, getattr(event, "dest_path", "") or ""]
        if any(relevant(event.event_type, str(p), event.is_directory) for p in paths if p):
            self._on_change()


class FolderWatcher:
    def __init__(
        self,
        db: Database,
        start_scan: Callable[[int], bool],
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
            due = self._state.due(set(watched), now)
        for library_id in due:
            with self._lock:
                after_change = self._state.pending_change(library_id)
            if self._start_scan(library_id):  # False: a scan is already running; retry
                with self._lock:
                    self._state.started(library_id, now, after_change)

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
                with self._lock:
                    self._state.forget(library_id)
        for library_id, path in wanted.items():
            if library_id in self._watches:
                continue
            try:
                handle = self._observer.schedule(
                    _Handler(partial(self.changed, library_id)), path, recursive=True
                )
            except OSError as exc:  # e.g. too many folders for inotify: polling still works
                logger.warning(
                    "can't watch a library folder; it is rescanned every 15 minutes instead",
                    extra={"library_id": library_id, "error": str(exc)},
                )
                handle = None
            self._watches[library_id] = (path, handle)
        return list(wanted)

    def changed(self, library_id: int) -> None:
        """Files in this library changed (inotify, or a Sonarr/Radarr webhook)."""
        with self._lock:
            self._state.changed(library_id, self._clock())
