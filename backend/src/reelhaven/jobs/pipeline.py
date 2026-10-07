"""Process one remux job: remux → verify → replace → record."""

import logging
import time
from datetime import timedelta
from pathlib import Path

from reelhaven import audit
from reelhaven.config import Settings
from reelhaven.db import Database, Job, JobResult, Library, MediaFile, RecycleItem
from reelhaven.db.types import utcnow
from reelhaven.jobs.commands import expected_layout, remux_command
from reelhaven.jobs.replace import (
    ReplaceError,
    Snapshot,
    check_unchanged,
    remove_tree,
    replace_with,
)
from reelhaven.jobs.runner import CancelledError, RunError, run_ffmpeg
from reelhaven.jobs.storage import recycle_path, work_dir
from reelhaven.jobs.verify import VerificationError, verify_output
from reelhaven.media.info import MediaInfo
from reelhaven.planner import Plan
from reelhaven.scanner import fingerprint

logger = logging.getLogger(__name__)

RECYCLE_DAYS = 14


class JobFailedError(Exception):
    pass


def _set(db: Database, job_id: int, **fields: object) -> None:
    with db.write() as session:
        job = session.get(Job, job_id)
        if job is not None:
            for key, value in fields.items():
                setattr(job, key, value)


def _is_cancelled(db: Database, job_id: int) -> bool:
    with db.read() as session:
        job = session.get(Job, job_id)
        return job is None or job.status == "cancelled"


def process(db: Database, settings: Settings, job_id: int) -> None:
    """Run a claimed job to completion. Never leaves a half-replaced file."""
    with db.read() as session:
        job = session.get(Job, job_id)
        if job is None:
            return
        library = session.get(Library, job.library_id)
        if library is None:
            raise JobFailedError("the library was removed")
        root = Path(library.path)
        source = Path(job.source_path)
        info = MediaInfo.model_validate(job.probe)
        plan = Plan.model_validate(job.plan)
        snapshot = Snapshot(job.source_size, job.source_mtime_ns)
        media_file_id = job.media_file_id
        library_name, actor = library.name, job.requested_by

    started = time.monotonic()
    workdir = work_dir(root, job_id)
    remove_tree(workdir)
    workdir.mkdir(parents=True)
    output = workdir / source.name
    try:
        check_unchanged(source, snapshot)
        duration = info.duration_s or 0.0
        last = [0.0]

        def progress(fraction: float, fps: float | None = None, speed: float | None = None) -> None:
            if fraction - last[0] >= 0.02 or fraction >= 1.0:
                last[0] = fraction
                _set(db, job_id, progress=round(fraction * 0.8, 3))  # remux = first 80 %

        run_ffmpeg(
            remux_command(settings.ffmpeg, source, output, info, plan),
            duration or None,
            timeout_s=600 + duration * 2,
            on_progress=progress,
            should_cancel=lambda: _is_cancelled(db, job_id),
        )
        _set(db, job_id, status="verifying", progress=0.8)
        new_info = verify_output(
            output,
            info,
            expected_layout(source, info, plan),
            settings.ffmpeg,
            settings.ffprobe,
            timeout_s=300 + duration,
        )
        if _is_cancelled(db, job_id):
            raise CancelledError

        relative = source.relative_to(root).as_posix()
        stored = recycle_path(root, f"job-{job_id}", relative)
        replace_with(source, output, stored, snapshot)
    except CancelledError:
        remove_tree(workdir)
        _set(db, job_id, finished_at=utcnow())
        return
    except (RunError, VerificationError, ReplaceError, OSError, ValueError) as exc:
        remove_tree(workdir)
        raise JobFailedError(str(exc)) from exc
    remove_tree(workdir)

    record_replacement(
        db,
        job_id=job_id,
        library_id=library.id,
        library_name=library_name,
        actor=actor,
        source=source,
        stored=stored,
        snapshot=snapshot,
        new_info=new_info,
        started=started,
        media_file_id=media_file_id,
    )


def record_replacement(
    db: Database,
    *,
    job_id: int,
    library_id: int,
    library_name: str,
    actor: str,
    source: Path,
    stored: Path,
    snapshot: Snapshot,
    new_info: MediaInfo,
    started: float,
    media_file_id: int | None,
    device: str | None = None,
    fps: float | None = None,
) -> None:
    """After a successful replace: recycle entry, result, refreshed file record, audit."""
    st = source.stat()
    now = utcnow()
    with db.write() as session:
        session.add(
            RecycleItem(
                library_id=library_id,
                job_id=job_id,
                original_path=str(source),
                stored_path=str(stored),
                size=snapshot.size,
                reason="replaced",
                created_at=now,
                expires_at=now + timedelta(days=RECYCLE_DAYS),
            )
        )
        session.add(
            JobResult(
                job_id=job_id,
                bytes_before=snapshot.size,
                bytes_after=st.st_size,
                duration_s=new_info.duration_s,
                process_seconds=round(time.monotonic() - started, 2),
                outcome="replaced",
                device=device,
                fps=fps,
            )
        )
        if media_file_id is not None:
            row = session.get(MediaFile, media_file_id)
            if row is not None:
                row.size = st.st_size
                row.mtime_ns = st.st_mtime_ns
                row.fingerprint = fingerprint(source, st.st_size, st.st_mtime_ns)
                row.probe = new_info.model_dump(mode="json")
                row.probe_error = None
                row.status = "ok"
                row.probed_at = now
        job = session.get(Job, job_id)
        if job is not None:
            job.status = "done"
            job.progress = 1.0
            job.finished_at = now
        audit.record(
            session,
            actor,
            "file.replaced",
            str(source),
            {"job": job_id, "library": library_name, "before": snapshot.size, "after": st.st_size},
        )
    logger.info(
        "replaced file",
        extra={"job": job_id, "path": str(source), "before": snapshot.size, "after": st.st_size},
    )
