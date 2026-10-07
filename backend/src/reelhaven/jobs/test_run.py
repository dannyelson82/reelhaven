"""Test runs (ADR-0020): encode one file into /transcode/test-run, measure its
quality and extract comparison stills. The original is never touched."""

import logging
import time
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from reelhaven import audit
from reelhaven.config import Settings
from reelhaven.db import Database, Job, Library, MediaFile, TestRun
from reelhaven.db.types import utcnow
from reelhaven.dryrun import plan_library
from reelhaven.encode_planner import profile_fingerprint
from reelhaven.encoders import Device
from reelhaven.jobs.encode_commands import encode_command, expected_encode_layout, expected_video
from reelhaven.jobs.pipeline import JobFailedError, _is_cancelled, _set
from reelhaven.jobs.replace import Snapshot, check_unchanged, remove_tree
from reelhaven.jobs.runner import CancelledError, RunError, run_ffmpeg
from reelhaven.jobs.service import NotApplicableError, library_profile
from reelhaven.jobs.verify import VerificationError, verify_output
from reelhaven.media.info import MediaInfo
from reelhaven.planner import Plan
from reelhaven.profiles import ProfileSettings
from reelhaven.quality_metrics import SEGMENT_SECONDS, extract_frame, measure, segment_starts

logger = logging.getLogger(__name__)

FRAME_WIDTH = 1280


def test_run_dir(settings: Settings, library_id: int, run_id: int | None = None) -> Path:
    base = settings.transcode_dir / "test-run" / str(library_id)
    return base if run_id is None else base / str(run_id)


def frame_path(settings: Settings, run: TestRun, index: int, which: str) -> Path:
    return test_run_dir(settings, run.library_id, run.id) / f"frame-{index}-{which}.jpg"


def create_test_run(
    db: Database, session: Session, library: Library, file_id: int | None, actor: str
) -> TestRun:
    """Plan a test run on ``file_id``, or on the largest file that would be re-encoded."""
    profile = library_profile(session, library)
    if profile is None:
        raise NotApplicableError("no_profile")
    candidates = [
        p for p in plan_library(db, library.id)
        if p.plan is not None and p.plan.action == "encode"
    ]  # fmt: skip
    if file_id is not None:
        candidates = [p for p in candidates if p.file_id == file_id]
        if not candidates:
            raise NotApplicableError("not_an_encode_candidate")
    if not candidates:
        raise NotApplicableError("nothing_to_encode")
    choice = max(candidates, key=lambda p: p.size)
    media_file = session.get(MediaFile, choice.file_id)
    assert media_file is not None and choice.plan is not None  # noqa: S101
    run = TestRun(
        library_id=library.id,
        media_file_id=media_file.id,
        profile=profile.model_dump(),
        profile_fingerprint=profile_fingerprint(profile),
        requested_by=actor,
    )
    session.add(run)
    session.flush()
    session.add(
        Job(
            library_id=library.id,
            media_file_id=media_file.id,
            test_run_id=run.id,
            type="test",
            priority=10,  # ahead of bulk work: the owner is waiting for it
            source_path=media_file.path,
            source_size=media_file.size,
            source_mtime_ns=media_file.mtime_ns,
            plan=choice.plan.model_dump(mode="json"),
            probe=media_file.probe or {},
            profile=profile.model_dump(),
            requested_by=actor,
        )
    )
    details = {"file": media_file.relative_path, "profile": run.profile_fingerprint}
    audit.record(session, actor, "test_run.started", library.name, details)
    return run


def process_test(db: Database, settings: Settings, job_id: int, device: Device) -> None:
    with db.read() as session:
        job = session.get(Job, job_id)
        if job is None or job.test_run_id is None or job.profile is None:
            return
        run = session.get(TestRun, job.test_run_id)
        if run is None:
            return
        source = Path(job.source_path)
        info = MediaInfo.model_validate(job.probe)
        plan = Plan.model_validate(job.plan)
        profile = ProfileSettings.model_validate(job.profile)
        snapshot = Snapshot(job.source_size, job.source_mtime_ns)
        run_id, library_id = run.id, run.library_id

    # Only the latest test run per library is kept on disk.
    remove_tree(test_run_dir(settings, library_id))
    folder = test_run_dir(settings, library_id, run_id)
    folder.mkdir(parents=True)
    encoded = folder / source.name
    started = time.monotonic()
    stats: dict[str, float] = {}
    try:
        check_unchanged(source, snapshot)
        duration = info.duration_s or 0.0

        def progress(fraction: float, fps: float | None = None, speed: float | None = None) -> None:
            if fps:
                stats["fps"] = fps
            _set(db, job_id, progress=round(fraction * 0.8, 3), fps=fps, speed=speed)

        run_ffmpeg(
            encode_command(settings.ffmpeg, device, source, encoded, info, plan, profile),
            duration or None,
            timeout_s=3600 + duration * 30,
            on_progress=progress,
            should_cancel=lambda: _is_cancelled(db, job_id),
        )
        _set(db, job_id, status="verifying", progress=0.8)
        target = expected_video(info, profile)
        new_info = verify_output(
            encoded, info, expected_encode_layout(source, info, plan, profile),
            settings.ffmpeg, settings.ffprobe, timeout_s=600 + duration, expected_video=target,
        )  # fmt: skip
        out_video = new_info.video
        assert out_video is not None and out_video.width is not None  # noqa: S101
        _set(db, job_id, progress=0.9)
        quality = measure(
            settings.ffmpeg, source, encoded, duration, out_video.width, target.height
        )
        times = [
            at
            for index, at in enumerate(frame_times(duration))
            if _stills(settings, source, encoded, folder, index, at)
        ]
    except CancelledError:
        remove_tree(folder)
        _finish(db, job_id, run_id, "failed", error="Cancelled.")
        return
    except Exception as exc:  # any failure must end the test run, never leave it "running"
        remove_tree(folder)
        _finish(db, job_id, run_id, "failed", error=str(exc)[:2000] or exc.__class__.__name__)
        if isinstance(exc, (RunError, VerificationError, OSError, ValueError)):
            raise JobFailedError(str(exc)) from exc
        raise

    before, after = snapshot.size, encoded.stat().st_size
    result: dict[str, Any] = {
        "bytes_before": before,
        "bytes_after": after,
        "savings_percent": round(100 * (1 - after / before), 1) if before else None,
        "min_savings_percent": profile.min_savings_percent,
        "xpsnr": quality.xpsnr,
        "ssim": quality.ssim,
        "rating": quality.rating,
        "frame_times": times,
        "codec": out_video.codec,
        "height_before": info.video.height if info.video else None,
        "height_after": out_video.height,
        "bit_depth": out_video.bit_depth,
        "hdr": out_video.hdr,
        "device": device.id,
        "fps": stats.get("fps"),
        "seconds": round(time.monotonic() - started, 1),
    }
    _finish(db, job_id, run_id, "done", result=result)


def frame_times(duration: float) -> list[float]:
    """Moments for comparison stills: the middle of each measured segment, inside the video."""
    if duration < SEGMENT_SECONDS * 1.5:
        return [round(duration / 2, 2)]
    last = max(duration - 0.5, 0.0)
    return [round(min(start + SEGMENT_SECONDS / 2, last), 2) for start in segment_starts(duration)]


def _stills(
    settings: Settings, source: Path, encoded: Path, folder: Path, index: int, at: float
) -> bool:
    """Extract both stills for one moment; a failure only means no picture for it."""
    try:
        for which, video in (("source", source), ("encoded", encoded)):
            extract_frame(
                settings.ffmpeg, video, at, folder / f"frame-{index}-{which}.jpg", FRAME_WIDTH
            )
    except Exception:
        logger.warning("could not extract a comparison still", extra={"at": at})
        return False
    return True


def _finish(
    db: Database,
    job_id: int,
    run_id: int,
    status: str,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    now = utcnow()
    with db.write() as session:
        run = session.get(TestRun, run_id)
        if run is not None:
            run.status = status
            run.result = result
            run.error = error
            run.finished_at = now
        job = session.get(Job, job_id)
        if job is not None and status == "done":
            job.status = "done"
            job.progress = 1.0
            job.finished_at = now


def approve(session: Session, run: TestRun, library: Library, actor: str) -> None:
    """The owner looked at the result and accepts the profile for bulk encoding."""
    if run.status != "done":
        raise NotApplicableError("test_run_not_finished")
    profile = library_profile(session, library)
    if profile is None or profile_fingerprint(profile) != run.profile_fingerprint:
        raise NotApplicableError("profile_changed")
    run.status = "approved"
    run.approved_by = actor
    run.approved_at = utcnow()
    library.test_run_profile = run.profile_fingerprint
    library.test_run_at = utcnow()
    audit.record(
        session, actor, "test_run.approved", library.name, {"profile": run.profile_fingerprint}
    )


def latest(session: Session, library_id: int) -> TestRun | None:
    return session.scalars(
        select(TestRun).where(TestRun.library_id == library_id).order_by(TestRun.id.desc()).limit(1)
    ).first()
