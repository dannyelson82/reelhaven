"""Automatic processing (ADR-0025): nightly rescans and topping up the queue.

The decisions are pure functions (``rescan_due``, ``pick``); ``Automation`` is
the background thread that applies them every 30 seconds.
"""

import logging
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from reelhaven import audit
from reelhaven.automation_settings import load
from reelhaven.db import Database, Job, Library, MediaFile
from reelhaven.dryrun import FilePlan, plan_library
from reelhaven.encode_planner import profile_fingerprint
from reelhaven.jobs.service import ACTIVE, create_jobs, library_profile

logger = logging.getLogger(__name__)

ACTOR = "automatic"
TOP_UP = 4  # at least this many queued + running jobs per automatic library
SPARE = 2  # queued beyond what the devices run at once, so none waits for the next round
TICK_S = 30.0


# --- pure decisions --------------------------------------------------------------------


def queue_target(encode_slots: int) -> int:
    """Jobs (queued + running) to keep per automatic library: enough to fill every enabled
    device's slots with a few spare, so no GPU sits idle waiting for the next round."""
    return max(TOP_UP, encode_slots + SPARE)


def rescan_due(last_scan: datetime | None, now: datetime, rescan_at: str) -> bool:
    """Whether today's scheduled rescan (local time) still has to run.

    ``last_scan`` and ``now`` are naive local times.
    """
    hours, minutes = (int(part) for part in rescan_at.split(":"))
    scheduled = datetime.combine(now.date(), time(hours, minutes))
    return now >= scheduled and (last_scan is None or last_scan < scheduled)


@dataclass(frozen=True)
class FileState:
    size: int
    mtime_ns: int


def pick(
    plans: Iterable[FilePlan],
    *,
    active: set[int],
    gave_up: dict[int, FileState],
    current: dict[int, FileState],
    encodes_allowed: bool,
    limit: int,
) -> list[FilePlan]:
    """Files to queue next for an automatic library, in library order.

    Skips files already queued or running, files whose last job failed or was
    cancelled and that haven't changed since (no automatic retries), and
    re-encodes until the library's profile has an approved test run. Files whose
    original language is still being looked up wait. Files needing review never
    have an encode or remux plan, so they're never picked.
    """
    chosen: list[FilePlan] = []
    for item in plans:
        if len(chosen) >= limit:
            break
        plan = item.plan
        if plan is None or plan.action not in ("remux", "encode"):
            continue
        if plan.action == "encode" and not encodes_allowed:
            continue
        if item.language_pending:
            continue
        if item.file_id in active:
            continue
        failed = gave_up.get(item.file_id)
        if failed is not None and failed == current.get(item.file_id):
            continue
        chosen.append(item)
    return chosen


# --- the background thread -----------------------------------------------------------------


class Automation:
    def __init__(
        self,
        db: Database,
        start_scan: Callable[[int], bool],
        notify_queue: Callable[[], None],
        clock: Callable[[], datetime] = datetime.now,
        encode_slots: Callable[[], int] = lambda: 0,
    ) -> None:
        self._db = db
        self._encode_slots = encode_slots
        self._start_scan = start_scan
        self._notify_queue = notify_queue
        self._clock = clock
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="automation", daemon=True)
        self._thread.start()

    def poke(self) -> None:
        """Run a round soon (e.g. a library was just switched to Automatic)."""
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(TICK_S)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                self.tick()
            except Exception:
                logger.exception("automation tick failed")

    def tick(self) -> None:
        """One round: due rescans, then top up automatic libraries."""
        with self._db.read() as session:
            settings = load(session)
            libraries = [
                (lib.id, lib.watch_mode, lib.last_scan_at)
                for lib in session.scalars(select(Library).where(Library.watch_mode != "off"))
            ]
        now = self._clock()
        if settings.rescan_enabled:
            for library_id, _mode, last_scan in libraries:
                local_last = last_scan.astimezone().replace(tzinfo=None) if last_scan else None
                if rescan_due(local_last, now, settings.rescan_at):
                    self._start_scan(library_id)
        if settings.paused:
            return
        queued = sum(self.top_up(lid) for lid, mode, _ in libraries if mode == "automatic")
        if queued:
            self._notify_queue()

    def top_up(self, library_id: int) -> int:
        """Fill one automatic library up to its queue target; returns how many were added."""
        with self._db.read() as session:
            library = session.get(Library, library_id)
            if library is None or library.watch_mode != "automatic":
                return 0
            active_jobs = set(
                session.scalars(
                    select(Job.media_file_id).where(
                        Job.library_id == library_id, Job.status.in_(ACTIVE)
                    )
                )
            )
            room = queue_target(self._encode_slots()) - len(active_jobs)
            if room <= 0:
                return 0
            profile = library_profile(session, library)
            encodes_allowed = profile is not None and library.test_run_profile == (
                profile_fingerprint(profile)
            )
            gave_up = _given_up(session, library_id)
            current = {
                f.id: FileState(f.size, f.mtime_ns)
                for f in session.scalars(
                    select(MediaFile).where(MediaFile.library_id == library_id)
                )
            }
        chosen = pick(
            plan_library(self._db, library_id),
            active={i for i in active_jobs if i is not None},
            gave_up=gave_up,
            current=current,
            encodes_allowed=encodes_allowed,
            limit=room,
        )
        if not chosen:
            return 0
        with self._db.write() as session:
            library = session.get(Library, library_id)
            if library is None or library.watch_mode != "automatic":
                return 0
            jobs = create_jobs(session, library, chosen, ACTOR)
            if jobs:
                audit.record(
                    session, ACTOR, "library.auto_queued", library.name, {"queued": len(jobs)}
                )
        return len(jobs)


def _given_up(session: Session, library_id: int) -> dict[int, FileState]:
    """Files whose most recent job failed or was cancelled, with the file state it saw."""
    latest: dict[int, Job] = {}
    for job in session.scalars(
        select(Job).where(Job.library_id == library_id, Job.media_file_id.is_not(None))
    ):
        assert job.media_file_id is not None  # noqa: S101
        if job.media_file_id not in latest or job.id > latest[job.media_file_id].id:
            latest[job.media_file_id] = job
    return {
        file_id: FileState(job.source_size, job.source_mtime_ns)
        for file_id, job in latest.items()
        if job.status in ("failed", "cancelled") and job.type != "test"
    }
