"""Process one remux job: remux → verify → replace → record."""

import logging
import time
from datetime import timedelta
from pathlib import Path

from reelhaven import audit
from reelhaven.config import Settings
from reelhaven.db import Database, Job, JobResult, Library, MediaFile, RecycleItem
from reelhaven.db.types import utcnow
from reelhaven.jobs.commands import (
    expected_layout,
    expected_remux_codecs,
    expected_remux_forced,
    remux_command,
)
from reelhaven.jobs.replace import (
    ReplaceError,
    Snapshot,
    check_unchanged,
    remove_tree,
    replace_with,
)
from reelhaven.jobs.runner import CancelledError, RunError, run_ffmpeg
from reelhaven.jobs.storage import delete_stored, recycle_path, work_dir
from reelhaven.jobs.verify import VerificationError, verify_output
from reelhaven.media.info import MediaInfo
from reelhaven.planner import Plan, conversion_signature, without_conversions
from reelhaven.recycle_settings import keep_days
from reelhaven.scanner import fingerprint

logger = logging.getLogger(__name__)


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

        def remux_and_verify(plan: Plan) -> MediaInfo:
            run_ffmpeg(
                remux_command(settings.ffmpeg, source, output, info, plan),
                duration or None,
                timeout_s=600 + duration * 2,
                on_progress=progress,
                should_cancel=lambda: _is_cancelled(db, job_id),
            )
            _set(db, job_id, status="verifying", progress=0.8)
            return verify_output(
                output,
                info,
                expected_layout(source, info, plan),
                settings.ffmpeg,
                settings.ffprobe,
                timeout_s=300 + duration,
                expected_codecs=expected_remux_codecs(source, info, plan),
                expected_forced=expected_remux_forced(source, info, plan),
            )

        new_info = remux_and_verify(plan)
        signature = conversion_signature(plan.tracks)
        attempt = output.stat().st_size
        if signature is not None and attempt >= snapshot.size:
            # Converting the audio didn't help: remember not to try it again, and still
            # carry out the track changes (languages, default and forced flags) if any.
            _remember_audio_no_gain(db, media_file_id, signature)
            output.unlink(missing_ok=True)
            plan = without_conversions(plan)
            if plan.action == "skip":
                remove_tree(workdir)
                _record_audio_no_gain(db, job_id, snapshot.size, attempt, started, actor, source)
                return
            last[0] = 0.0
            _set(db, job_id, status="running", progress=0.0)
            new_info = remux_and_verify(plan)
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
    keep = keep_days(db)
    with db.write() as session:
        item = RecycleItem(
            library_id=library_id,
            job_id=job_id,
            original_path=str(source),
            stored_path=str(stored),
            size=snapshot.size,
            reason="replaced",
            created_at=now,
            expires_at=now + timedelta(days=keep),
        )
        session.add(item)
        session.flush()
        item_id = item.id
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
    if keep == 0:
        discard_now(db, item_id)


def discard_now(db: Database, item_id: int) -> None:
    """Recycle bin off (ADR-0028): delete a recycled file straight away.

    The item was saved as already expired, so if this fails (or ReelHaven stops
    first) the regular purge removes it.
    """
    with db.read() as session:
        item = session.get(RecycleItem, item_id)
        if item is None:
            return
        stored, original = Path(item.stored_path), item.original_path
    try:
        delete_stored(stored)
    except OSError:
        logger.warning("could not delete a recycled original", extra={"item": item_id})
        return
    with db.write() as session:
        row = session.get(RecycleItem, item_id)
        if row is not None and row.purged_at is None:
            row.purged_at = utcnow()
            audit.record(session, "system", "recycle.skipped", original, {"item": item_id})


def _remember_audio_no_gain(db: Database, media_file_id: int | None, signature: str) -> None:
    """The planner won't convert this file's audio this way again."""
    if media_file_id is None:
        return
    with db.write() as session:
        row = session.get(MediaFile, media_file_id)
        if row is not None:
            row.no_gain_audio = signature


def _record_audio_no_gain(
    db: Database, job_id: int, before: int, after: int, started: float, actor: str, source: Path
) -> None:
    """Converting the audio was the only change and it didn't help: the original stays."""
    with db.write() as session:
        session.add(
            JobResult(
                job_id=job_id, bytes_before=before, bytes_after=after, duration_s=None,
                process_seconds=round(time.monotonic() - started, 2), outcome="no_gain",
            )
        )  # fmt: skip
        job = session.get(Job, job_id)
        if job is not None:
            job.status = "done"
            job.progress = 1.0
            job.finished_at = utcnow()
        audit.record(session, actor, "file.no_gain", str(source),
                     {"job": job_id, "before": before, "after": after})  # fmt: skip
    logger.info(
        "converting the audio saved nothing; original kept",
        extra={"job": job_id, "path": str(source)},
    )
