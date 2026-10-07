"""Process one encode job on a device: encode → verify → no-gain check →
copy into the library → replace → record (ADR-0016, ADR-0020)."""

import logging
import os
import shutil
import time
from pathlib import Path

from reelhaven import audit
from reelhaven.config import Settings
from reelhaven.db import Database, Job, JobResult, Library, MediaFile
from reelhaven.db.types import utcnow
from reelhaven.encode_planner import profile_fingerprint
from reelhaven.encoders import Device
from reelhaven.jobs.encode_commands import (
    encode_command,
    expected_codecs,
    expected_encode_layout,
    expected_video,
)
from reelhaven.jobs.pipeline import JobFailedError, _is_cancelled, _set, record_replacement
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
from reelhaven.profiles import ProfileSettings

logger = logging.getLogger(__name__)


def transcode_dir(settings: Settings, job_id: int) -> Path:
    return settings.transcode_dir / "jobs" / str(job_id)


def _copy_into(source: Path, target: Path) -> None:
    """Copy the verified encode next to the original, flushed to disk."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, target.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=8 * 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    if target.stat().st_size != source.stat().st_size:
        raise ReplaceError("copying the new file into the library failed (size mismatch)")


def process_encode(db: Database, settings: Settings, job_id: int, device: Device) -> None:
    with db.read() as session:
        job = session.get(Job, job_id)
        if job is None:
            return
        library = session.get(Library, job.library_id)
        if library is None:
            raise JobFailedError("the library was removed")
        if job.profile is None:
            raise JobFailedError("encode job without a profile")
        root = Path(library.path)
        source = Path(job.source_path)
        info = MediaInfo.model_validate(job.probe)
        plan = Plan.model_validate(job.plan)
        profile = ProfileSettings.model_validate(job.profile)
        snapshot = Snapshot(job.source_size, job.source_mtime_ns)
        media_file_id, library_name, actor = job.media_file_id, library.name, job.requested_by
        library_id = library.id

    started = time.monotonic()
    scratch = transcode_dir(settings, job_id)
    workdir = work_dir(root, job_id)
    for folder in (scratch, workdir):
        remove_tree(folder)
    scratch.mkdir(parents=True)
    encoded = scratch / source.name
    speed_stats: dict[str, float] = {}

    def cleanup() -> None:
        remove_tree(scratch)
        remove_tree(workdir)

    try:
        check_unchanged(source, snapshot)
        duration = info.duration_s or 0.0
        last = [0.0]

        def progress(fraction: float, fps: float | None = None, speed: float | None = None) -> None:
            if fps:
                speed_stats["fps"] = fps
            if fraction - last[0] >= 0.01 or fraction >= 1.0:
                last[0] = fraction
                _set(db, job_id, progress=round(fraction * 0.85, 3), fps=fps, speed=speed)

        run_ffmpeg(
            encode_command(settings.ffmpeg, device, source, encoded, info, plan, profile),
            duration or None,
            # Generous: a slow CPU encode of a long film can take many hours.
            timeout_s=3600 + duration * 30,
            on_progress=progress,
            should_cancel=lambda: _is_cancelled(db, job_id),
        )
        _set(db, job_id, status="verifying", progress=0.85)
        new_info = verify_output(
            encoded,
            info,
            expected_encode_layout(source, info, plan, profile),
            settings.ffmpeg,
            settings.ffprobe,
            timeout_s=600 + duration,
            expected_video=expected_video(info, profile),
            expected_codecs=expected_codecs(source, info, plan, profile),
        )
        if _is_cancelled(db, job_id):
            raise CancelledError

        # No gain: keep the original and don't try this profile on it again.
        limit = snapshot.size * (1 - profile.min_savings_percent / 100)
        if encoded.stat().st_size > limit:
            _record_no_gain(db, job_id, media_file_id, profile, snapshot.size,
                            encoded.stat().st_size, started, device.id, speed_stats.get("fps"),
                            actor, source)  # fmt: skip
            cleanup()
            return

        _set(db, job_id, progress=0.92)
        staged = workdir / source.name
        _copy_into(encoded, staged)
        remove_tree(scratch)
        relative = source.relative_to(root).as_posix()
        stored = recycle_path(root, f"job-{job_id}", relative)
        replace_with(source, staged, stored, snapshot)
    except CancelledError:
        cleanup()
        _set(db, job_id, finished_at=utcnow())
        return
    except (RunError, VerificationError, ReplaceError, OSError, ValueError) as exc:
        cleanup()
        raise JobFailedError(str(exc)) from exc
    cleanup()
    record_replacement(
        db,
        job_id=job_id,
        library_id=library_id,
        library_name=library_name,
        actor=actor,
        source=source,
        stored=stored,
        snapshot=snapshot,
        new_info=new_info,
        started=started,
        media_file_id=media_file_id,
        device=device.id,
        fps=speed_stats.get("fps"),
    )


def _record_no_gain(
    db: Database,
    job_id: int,
    media_file_id: int | None,
    profile: ProfileSettings,
    before: int,
    after: int,
    started: float,
    device: str,
    fps: float | None,
    actor: str,
    source: Path,
) -> None:
    now = utcnow()
    with db.write() as session:
        session.add(
            JobResult(
                job_id=job_id, bytes_before=before, bytes_after=after, duration_s=None,
                process_seconds=round(time.monotonic() - started, 2), outcome="no_gain",
                device=device, fps=fps,
            )
        )  # fmt: skip
        if media_file_id is not None:
            row = session.get(MediaFile, media_file_id)
            if row is not None:
                row.no_gain_profile = profile_fingerprint(profile)
        job = session.get(Job, job_id)
        if job is not None:
            job.status = "done"
            job.progress = 1.0
            job.finished_at = now
        audit.record(session, actor, "file.no_gain", str(source),
                     {"job": job_id, "before": before, "after": after})  # fmt: skip
    logger.info(
        "encode saved too little; original kept", extra={"job": job_id, "path": str(source)}
    )
