"""Library scanner (ARCHITECTURE.md §6.1).

Walks a library, finds video files, recognises unchanged and moved files by
fingerprint, probes new or changed ones and stores the results. Read-only
on disk: it never changes a media file.
"""

import hashlib
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete, select

from reelhaven.config import Settings
from reelhaven.db import Database, Library, MediaFile
from reelhaven.db.types import utcnow
from reelhaven.media.probe import ProbeError, probe
from reelhaven.paths import INTERNAL_DIR, PathNotAllowedError, resolve_within

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = frozenset(
    {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".ts", ".m2ts", ".webm", ".wmv", ".mpg", ".mpeg"}
)
# Folders that hold extras rather than the main titles (case-insensitive).
IGNORED_FOLDERS = frozenset(
    {
        "sample",
        "samples",
        "extras",
        "featurettes",
        "behind the scenes",
        "deleted scenes",
        "interviews",
        "scenes",
        "shorts",
        "trailers",
        "other",
        "@eadir",
        "#recycle",
        "#snapshot",
        "lost+found",
    }
)
_SAMPLE_FILE = re.compile(r"(^|[ ._-])sample([ ._-]|$)", re.IGNORECASE)
_EXTRAS_SUFFIX = re.compile(
    r"-(trailer|sample|featurette|behindthescenes|deleted|interview|scene|short|other)$",
    re.IGNORECASE,
)
FINGERPRINT_CHUNK = 64 * 1024
PROBE_WORKERS = 4
WRITE_BATCH = 50


def fingerprint(path: Path, size: int, mtime_ns: int) -> str:
    """size + mtime + hash of the first and last 64 KiB (ARCHITECTURE.md §6.1)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        digest.update(handle.read(FINGERPRINT_CHUNK))
        if size > FINGERPRINT_CHUNK:
            handle.seek(max(size - FINGERPRINT_CHUNK, FINGERPRINT_CHUNK))
            digest.update(handle.read(FINGERPRINT_CHUNK))
    return f"{size}:{mtime_ns}:{digest.hexdigest()[:32]}"


def content_key(fp: str) -> str:
    """The part of a fingerprint that survives a move (mtime may change)."""
    size, _mtime, digest = fp.split(":", 2)
    return f"{size}:{digest}"


def is_ignored_file(name: str) -> bool:
    stem, ext = Path(name).stem, Path(name).suffix
    return (
        name.startswith(".")
        or ext.lower() not in VIDEO_EXTENSIONS
        or bool(_SAMPLE_FILE.search(stem))
        or bool(_EXTRAS_SUFFIX.search(stem))
    )


@dataclass
class Found:
    path: Path
    relative: str
    size: int
    mtime_ns: int


def walk(root: Path, stable_seconds: float, now: float) -> tuple[list[Found], int]:
    """Video files under ``root``; also returns how many were skipped as still changing."""
    found: list[Found] = []
    unstable = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            d
            for d in dirnames
            if not d.startswith(".") and d != INTERNAL_DIR and d.casefold() not in IGNORED_FOLDERS
        )
        for name in sorted(filenames):
            if is_ignored_file(name):
                continue
            full = Path(dirpath) / name
            try:
                real = resolve_within(root, full)  # symlinked files must stay inside
                st = real.stat()
            except (PathNotAllowedError, OSError):
                continue
            if not real.is_file():
                continue
            if now - st.st_mtime < stable_seconds:
                unstable += 1  # probably still being copied; next scan picks it up
                continue
            found.append(Found(real, real.relative_to(root).as_posix(), st.st_size, st.st_mtime_ns))
    return found, unstable


@dataclass
class ScanProgress:
    library_id: int
    state: str = "scanning"  # scanning | done | error
    phase: str = "listing"  # listing | probing | saving
    found: int = 0
    to_probe: int = 0
    probed: int = 0
    failed: int = 0
    unchanged: int = 0
    moved: int = 0
    removed: int = 0
    unstable: int = 0
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None


class Scanner:
    """Runs one background scan per library at a time."""

    def __init__(self, db: Database, settings: Settings, stable_seconds: float = 120) -> None:
        self._db = db
        self._settings = settings
        self._stable_seconds = stable_seconds
        self._lock = threading.Lock()
        self._progress: dict[int, ScanProgress] = {}
        self._threads: dict[int, threading.Thread] = {}

    def progress(self, library_id: int) -> ScanProgress | None:
        with self._lock:
            return self._progress.get(library_id)

    def is_running(self, library_id: int) -> bool:
        with self._lock:
            thread = self._threads.get(library_id)
            return thread is not None and thread.is_alive()

    def start(self, library_id: int) -> bool:
        """Start a scan; returns False if one is already running for this library."""
        with self._lock:
            thread = self._threads.get(library_id)
            if thread is not None and thread.is_alive():
                return False
            self._progress[library_id] = ScanProgress(library_id)
            thread = threading.Thread(
                target=self._run, args=(library_id,), name=f"scan-{library_id}", daemon=True
            )
            self._threads[library_id] = thread
            thread.start()
            return True

    def wait(self, library_id: int, timeout: float | None = None) -> None:
        thread = self._threads.get(library_id)
        if thread is not None:
            thread.join(timeout)

    def _run(self, library_id: int) -> None:
        progress = self._progress[library_id]
        try:
            self.scan(library_id, progress)
            progress.state = "done"
            error = None
        except Exception as exc:
            logger.exception("scan failed", extra={"library_id": library_id})
            progress.state = "error"
            progress.error = error = str(exc)[:500] or exc.__class__.__name__
        progress.finished_at = time.time()
        with self._db.write() as session:
            library = session.get(Library, library_id)
            if library is not None:
                library.last_scan_at = utcnow()
                library.last_scan_error = error

    def scan(self, library_id: int, progress: ScanProgress) -> None:
        with self._db.read() as session:
            library = session.get(Library, library_id)
            if library is None:
                raise LookupError("library no longer exists")
            root = Path(library.path)
            existing = {
                row.path: (row.id, row.size, row.mtime_ns, row.fingerprint, row.status)
                for row in session.scalars(
                    select(MediaFile).where(MediaFile.library_id == library_id)
                )
            }
        if not root.is_dir():
            raise FileNotFoundError(f"library folder is missing: {root}")

        found, progress.unstable = walk(root, self._stable_seconds, time.time())
        progress.found = len(found)
        seen = {f.path.as_posix() for f in found}
        vanished = {p: v for p, v in existing.items() if p not in seen}
        vanished_by_content = {content_key(v[3]): (p, v) for p, v in vanished.items()}

        to_probe: list[tuple[Found, str]] = []
        moves: list[tuple[int, Found, str]] = []
        touched: list[int] = []
        for item in found:
            key = item.path.as_posix()
            known = existing.get(key)
            if known is not None and known[1] == item.size and known[2] == item.mtime_ns:
                touched.append(known[0])
                progress.unchanged += 1
                continue
            fp = fingerprint(item.path, item.size, item.mtime_ns)
            if known is None:  # a new path might be a file that moved
                moved_from = vanished_by_content.get(content_key(fp))
                if moved_from is not None and moved_from[1][4] == "ok":
                    del vanished_by_content[content_key(fp)]
                    del vanished[moved_from[0]]
                    moves.append((moved_from[1][0], item, fp))
                    progress.moved += 1
                    continue
            to_probe.append((item, fp))
        progress.to_probe = len(to_probe)

        self._save_unchanged_and_moves(touched, moves)
        progress.phase = "probing"
        self._probe_and_save(library_id, to_probe, progress)

        progress.phase = "saving"
        if vanished:
            ids = [v[0] for v in vanished.values()]
            with self._db.write() as session:
                session.execute(delete(MediaFile).where(MediaFile.id.in_(ids)))
            progress.removed = len(ids)

    def _save_unchanged_and_moves(
        self, touched: list[int], moves: list[tuple[int, Found, str]]
    ) -> None:
        now = utcnow()
        for start in range(0, len(touched), 500):
            with self._db.write() as session:
                for row in session.scalars(
                    select(MediaFile).where(MediaFile.id.in_(touched[start : start + 500]))
                ):
                    row.last_seen_at = now
        if moves:
            with self._db.write() as session:
                for row_id, item, fp in moves:
                    moved = session.get(MediaFile, row_id)
                    if moved is not None:
                        moved.path = item.path.as_posix()
                        moved.relative_path = item.relative
                        moved.mtime_ns = item.mtime_ns
                        moved.fingerprint = fp
                        moved.last_seen_at = now

    def _probe_and_save(
        self, library_id: int, items: list[tuple[Found, str]], progress: ScanProgress
    ) -> None:
        settings = self._settings

        def work(
            item: tuple[Found, str],
        ) -> tuple[Found, str, dict[str, object] | None, str | None]:
            found, fp = item
            try:
                info = probe(found.path, settings.ffprobe, settings.probe_timeout_s)
                return found, fp, info.model_dump(mode="json"), None
            except ProbeError as exc:
                return found, fp, None, str(exc)[:1000]

        batch: list[tuple[Found, str, dict[str, object] | None, str | None]] = []
        with ThreadPoolExecutor(max_workers=PROBE_WORKERS, thread_name_prefix="probe") as pool:
            for result in pool.map(work, items):
                batch.append(result)
                progress.probed += 1
                if result[3] is not None:
                    progress.failed += 1
                if len(batch) >= WRITE_BATCH:
                    self._save_probed(library_id, batch)
                    batch = []
        if batch:
            self._save_probed(library_id, batch)

    def _save_probed(
        self, library_id: int, batch: list[tuple[Found, str, dict[str, object] | None, str | None]]
    ) -> None:
        now = utcnow()
        with self._db.write() as session:
            for found, fp, info, error in batch:
                key = found.path.as_posix()
                row: MediaFile | None = session.scalars(
                    select(MediaFile).where(MediaFile.path == key)
                ).first()
                if row is None:
                    row = MediaFile(library_id=library_id, path=key, first_seen_at=now)
                    session.add(row)
                row.relative_path = found.relative
                row.size = found.size
                row.mtime_ns = found.mtime_ns
                row.fingerprint = fp
                row.status = "ok" if error is None else "probe_failed"
                row.probe = info
                row.probe_error = error
                row.last_seen_at = now
                row.probed_at = now
