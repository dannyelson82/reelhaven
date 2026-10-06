"""Persistent job queue with a CPU worker pool for remux jobs (ADR-0004)."""

import logging
import threading
from pathlib import Path

from sqlalchemy import select, update

from reelhaven.config import Settings
from reelhaven.db import Database, Job, Library
from reelhaven.db.types import utcnow
from reelhaven.jobs.pipeline import JobFailedError, process
from reelhaven.jobs.replace import remove_tree
from reelhaven.jobs.storage import internal_dir

logger = logging.getLogger(__name__)


class JobQueue:
    def __init__(self, db: Database, settings: Settings, workers: int = 2) -> None:
        self._db = db
        self._settings = settings
        self._workers = workers
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._claim_lock = threading.Lock()
        self._idle = threading.Condition()
        self._active = 0

    # --- lifecycle -------------------------------------------------------------------

    def recover(self) -> None:
        """At startup: interrupted jobs start again from the beginning (§6.5)."""
        with self._db.write() as session:
            session.execute(
                update(Job)
                .where(Job.status.in_(("running", "verifying")))
                .values(status="queued", progress=0.0, started_at=None)
            )
            roots = [Path(p) for p in session.scalars(select(Library.path))]
        for root in roots:
            remove_tree(internal_dir(root) / "work")  # partial outputs from a crash

    def start(self) -> None:
        self.recover()
        for n in range(self._workers):
            thread = threading.Thread(target=self._loop, name=f"remux-{n}", daemon=True)
            thread.start()
            self._threads.append(thread)

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
                lambda: self._active == 0 and not self._has_queued(), timeout
            )

    # --- work --------------------------------------------------------------------------

    def _has_queued(self) -> bool:
        with self._db.read() as session:
            return session.scalar(select(Job.id).where(Job.status == "queued").limit(1)) is not None

    def _claim(self) -> int | None:
        with self._claim_lock, self._db.write() as session:
            job = session.scalars(
                select(Job)
                .where(Job.status == "queued")
                .order_by(Job.priority.desc(), Job.id)
                .limit(1)
            ).first()
            if job is None:
                return None
            job.status = "running"
            job.started_at = utcnow()
            job.progress = 0.0
            job.error = None
            return job.id

    def _loop(self) -> None:
        while not self._stop.is_set():
            # Count as busy *before* claiming, so wait_idle never sees a claimed
            # job that nobody is counted as working on.
            with self._idle:
                self._active += 1
            job_id = self._claim()
            if job_id is None:
                with self._idle:
                    self._active -= 1
                    self._idle.notify_all()
                self._wake.wait(timeout=5)
                self._wake.clear()
                continue
            try:
                process(self._db, self._settings, job_id)
            except JobFailedError as exc:
                self._fail(job_id, str(exc))
            except Exception as exc:
                logger.exception("job crashed", extra={"job": job_id})
                self._fail(job_id, f"unexpected error: {exc}")
            finally:
                with self._idle:
                    self._active -= 1
                    self._idle.notify_all()

    def _fail(self, job_id: int, error: str) -> None:
        logger.warning("job failed", extra={"job": job_id, "error": error[:300]})
        with self._db.write() as session:
            job = session.get(Job, job_id)
            if job is not None and job.status != "cancelled":
                job.status = "failed"
                job.error = error[:4000]
                job.finished_at = utcnow()
