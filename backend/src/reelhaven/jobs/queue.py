"""Persistent job queue (ADR-0004, ARCHITECTURE.md §6.5).

- Remux jobs run in a small CPU pool.
- Encode jobs run in one pool per device; a device only takes jobs whose codec
  and bit depth it proved it can encode (devices.py), and runs as many at once
  as its settings allow.
"""

import logging
import threading
from collections.abc import Callable
from functools import partial
from pathlib import Path

from sqlalchemy import select, update

from reelhaven import device_settings
from reelhaven.automation_settings import is_paused
from reelhaven.config import Settings
from reelhaven.db import Database, Job, Library
from reelhaven.db.types import utcnow
from reelhaven.devices import DeviceRegistry, DeviceReport
from reelhaven.encoders import Device
from reelhaven.jobs.encode_pipeline import process_encode
from reelhaven.jobs.pipeline import JobFailedError, process
from reelhaven.jobs.replace import remove_tree
from reelhaven.jobs.storage import internal_dir
from reelhaven.jobs.test_run import process_test

logger = logging.getLogger(__name__)

MAX_SLOTS = 8  # per device; the configured concurrency decides how many are used


def job_needs(job: Job) -> tuple[str, bool] | None:
    """(codec, ten_bit) an encode job needs from a device; None for remux jobs."""
    if job.type not in ("encode", "test"):
        return None
    video = (job.plan or {}).get("video") or {}
    return str(video.get("codec") or "hevc"), bool(video.get("ten_bit"))


class JobQueue:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        devices: DeviceRegistry | None = None,
        workers: int = 2,
    ) -> None:
        self._db = db
        self._settings = settings
        self._devices = devices
        self._workers = workers
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._slots: set[tuple[str, int]] = set()
        self._claim_lock = threading.Lock()
        self._idle = threading.Condition()
        self._active = 0
        # Called after every job (e.g. so Automatic can queue the next one at once).
        self.on_job_finished: Callable[[], None] = lambda: None

    # --- lifecycle -------------------------------------------------------------------

    def recover(self) -> None:
        """At startup: interrupted jobs start again from the beginning (§6.5)."""
        with self._db.write() as session:
            session.execute(
                update(Job)
                .where(Job.status.in_(("running", "verifying")))
                .values(status="queued", progress=0.0, started_at=None, device=None)
            )
            roots = [Path(p) for p in session.scalars(select(Library.path))]
        for root in roots:
            remove_tree(internal_dir(root) / "work")  # partial outputs from a crash
        remove_tree(self._settings.transcode_dir / "jobs")

    def start(self) -> None:
        self.recover()
        for n in range(self._workers):
            self._spawn(f"remux-{n}", lambda: self._claim(("remux",)), self._run_remux)
        if self._devices is not None:
            self._spawn("encode-manager", None, None)

    def stop(self, timeout: float = 5) -> None:
        self._stop.set()
        self._wake.set()
        for thread in self._threads:
            thread.join(timeout)

    def notify(self) -> None:
        self._wake.set()

    def wait_idle(self, timeout: float = 60) -> bool:
        """Block until no job is queued or running (used by tests)."""
        with self._idle:
            return self._idle.wait_for(
                lambda: self._active == 0 and not self._has_runnable(), timeout
            )

    # --- threads ------------------------------------------------------------------------

    def _spawn(
        self,
        name: str,
        claim: Callable[[], int | None] | None,
        run: Callable[[int], None] | None,
    ) -> None:
        target = self._manage_devices if claim is None else lambda: self._loop(claim, run)  # type: ignore[arg-type]
        thread = threading.Thread(target=target, name=name, daemon=True)
        thread.start()
        self._threads.append(thread)

    def _manage_devices(self) -> None:
        """Start encode workers for devices as they are detected."""
        while not self._stop.is_set():
            assert self._devices is not None  # noqa: S101
            for device, report in self._devices.usable():
                for slot in range(MAX_SLOTS):
                    key = (device.id, slot)
                    if key in self._slots:
                        continue
                    self._slots.add(key)
                    self._spawn(
                        f"encode-{device.id}-{slot}",
                        partial(self._claim_encode, device, report, slot),
                        partial(self._run_encode, device=device),
                    )
            self._stop.wait(5)

    def _loop(self, claim: Callable[[], int | None], run: Callable[[int], None]) -> None:
        while not self._stop.is_set():
            # Count as busy *before* claiming, so wait_idle never sees a claimed
            # job that nobody is counted as working on.
            with self._idle:
                self._active += 1
            job_id = claim()
            if job_id is None:
                with self._idle:
                    self._active -= 1
                    self._idle.notify_all()
                self._wake.wait(timeout=5)
                self._wake.clear()
                continue
            try:
                run(job_id)
            except JobFailedError as exc:
                self._fail(job_id, str(exc))
            except Exception as exc:
                logger.exception("job crashed", extra={"job": job_id})
                self._fail(job_id, f"unexpected error: {exc}")
            finally:
                with self._idle:
                    self._active -= 1
                    self._idle.notify_all()
                self._wake.set()  # another worker may now have something to do
                try:
                    self.on_job_finished()
                except Exception:
                    logger.exception("after-job hook failed")

    def _run_remux(self, job_id: int) -> None:
        process(self._db, self._settings, job_id)

    def _run_encode(self, job_id: int, device: Device) -> None:
        with self._db.read() as session:
            job = session.get(Job, job_id)
            is_test = job is not None and job.type == "test"
        if is_test:
            process_test(self._db, self._settings, job_id, device)
        else:
            process_encode(self._db, self._settings, job_id, device)

    # --- claiming -----------------------------------------------------------------------

    def _queued(self, session: object, types: tuple[str, ...]) -> list[Job]:
        return list(
            session.scalars(  # type: ignore[attr-defined]
                select(Job)
                .where(Job.status == "queued", Job.type.in_(types))
                .order_by(Job.priority.desc(), Job.id)
                .limit(200)
            )
        )

    def _claim(
        self,
        types: tuple[str, ...],
        accept: Callable[[Job], bool] = lambda _: True,
        device: str | None = None,
    ) -> int | None:
        if is_paused(self._db):
            return None  # ADR-0025: paused, so nothing new starts; running jobs finish
        with self._claim_lock, self._db.write() as session:
            for job in self._queued(session, types):
                if accept(job):
                    job.status = "running"
                    job.started_at = utcnow()
                    job.progress = 0.0
                    job.error = None
                    job.device = device
                    job.decoder = None
                    return job.id
        return None

    def _claim_encode(self, device: Device, report: DeviceReport, slot: int) -> int | None:
        with self._db.read() as session:
            settings = device_settings.load(session)
        if device.kind == "cpu":
            enabled, concurrency = settings.cpu_enabled, settings.cpu_concurrency
        else:
            config = settings.config_for(device.id)
            enabled, concurrency = config.enabled, config.concurrency
        if not enabled or slot >= concurrency:
            return None

        def capable(job: Job) -> bool:
            needs = job_needs(job)
            return needs is not None and report.supports(*needs)

        return self._claim(("encode", "test"), capable, device.id)

    def _has_runnable(self) -> bool:
        """Queued jobs that some enabled worker could take right now."""
        if is_paused(self._db):
            return False
        with self._db.read() as session:
            queued = self._queued(session, ("remux", "encode", "test"))
            settings = device_settings.load(session)
        if any(job.type == "remux" for job in queued):
            return True
        if self._devices is None:
            return False
        for device, report in self._devices.usable():
            enabled = (
                settings.cpu_enabled
                if device.kind == "cpu"
                else settings.config_for(device.id).enabled
            )
            if enabled and any(
                (needs := job_needs(job)) is not None and report.supports(*needs) for job in queued
            ):
                return True
        return False

    def encode_slots(self) -> int:
        """How many encodes the enabled devices run at once, all together."""
        if self._devices is None:
            return 0
        with self._db.read() as session:
            settings = device_settings.load(session)
        total = 0
        for device, _report in self._devices.usable():
            if device.kind == "cpu":
                total += settings.cpu_concurrency if settings.cpu_enabled else 0
            else:
                config = settings.config_for(device.id)
                total += config.concurrency if config.enabled else 0
        return total

    def _fail(self, job_id: int, error: str) -> None:
        logger.warning("job failed", extra={"job": job_id, "error": error[:300]})
        with self._db.write() as session:
            job = session.get(Job, job_id)
            if job is not None and job.status != "cancelled":
                job.status = "failed"
                job.error = error[:4000]
                job.finished_at = utcnow()
