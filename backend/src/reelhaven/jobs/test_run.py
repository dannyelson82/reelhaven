"""Test runs (ADR-0020, ADR-0021): encode a few sample files into
/transcode/test-run, measure their quality and extract comparison stills.
Originals are never touched."""

import logging
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from reelhaven import audit
from reelhaven.config import Settings
from reelhaven.db import Database, Job, Library, MediaFile, TestRun, TestRunSample
from reelhaven.db.types import utcnow
from reelhaven.dryrun import plan_library
from reelhaven.encode_planner import profile_fingerprint
from reelhaven.encoders import Device
from reelhaven.jobs.encode_commands import (
    expected_codecs,
    expected_encode_layout,
    expected_forced,
    expected_video,
)
from reelhaven.jobs.encode_run import run_encode
from reelhaven.jobs.pipeline import JobFailedError, _is_cancelled, _set
from reelhaven.jobs.replace import Snapshot, check_unchanged, remove_tree
from reelhaven.jobs.runner import CancelledError, RunError
from reelhaven.jobs.service import NotApplicableError, library_profile
from reelhaven.jobs.verify import VerificationError, verify_output
from reelhaven.media.info import MediaInfo
from reelhaven.planner import Plan
from reelhaven.profiles import ProfileSettings
from reelhaven.quality_metrics import extract_clip, extract_frame, measure
from reelhaven.sampling import MAX_SAMPLES, Candidate, choose_samples

logger = logging.getLogger(__name__)

MAX_STILL_WIDTH = 3840  # stills are full size, up to 4K
STILLS = 5
CLIP_SECONDS = 15.0  # comparison clips: the same scene from both files (ADR-0031)
_ENDED_JOB = ("failed", "cancelled")


def test_run_dir(settings: Settings, library_id: int, run_id: int | None = None) -> Path:
    base = settings.transcode_dir / "test-run" / str(library_id)
    return base if run_id is None else base / str(run_id)


def sample_dir(settings: Settings, library_id: int, run_id: int, sample_id: int) -> Path:
    return test_run_dir(settings, library_id, run_id) / str(sample_id)


def frame_path(settings: Settings, run: TestRun, sample_id: int, index: int, which: str) -> Path:
    """A still's file: lossless WebP since 0.8; older runs have JPEGs."""
    folder = sample_dir(settings, run.library_id, run.id, sample_id)
    webp = folder / f"frame-{index}-{which}.webp"
    return webp if webp.is_file() else folder / f"frame-{index}-{which}.jpg"


def clip_path(settings: Settings, run: TestRun, sample_id: int, which: str) -> Path:
    folder = sample_dir(settings, run.library_id, run.id, sample_id)
    return folder / f"clip-{which}.mp4"


def sample_status(sample: TestRunSample, job_status: str | None) -> str:
    """A sample whose job was cancelled or failed before it could report counts as failed."""
    if sample.status == "running" and job_status in _ENDED_JOB:
        return "failed"
    return sample.status


def run_status(run: TestRun, sample_statuses: Iterable[str]) -> str:
    """running until every sample has ended; then done, or failed if any sample failed."""
    if run.status == "approved":
        return "approved"
    statuses = list(sample_statuses)
    if not statuses or "running" in statuses:
        return "running"
    return "failed" if "failed" in statuses else "done"


def samples_of(session: Session, run: TestRun) -> list[tuple[TestRunSample, Job | None]]:
    samples = session.scalars(
        select(TestRunSample)
        .where(TestRunSample.test_run_id == run.id)
        .order_by(TestRunSample.position)
    ).all()
    jobs = {
        job.test_run_sample_id: job
        for job in session.scalars(
            select(Job).where(Job.test_run_sample_id.in_([s.id for s in samples]))
        )
    }
    return [(sample, jobs.get(sample.id)) for sample in samples]


def current_status(session: Session, run: TestRun) -> str:
    return run_status(
        run, (sample_status(s, job.status if job else None) for s, job in samples_of(session, run))
    )


def create_test_run(
    db: Database,
    session: Session,
    library: Library,
    file_id: int | None,
    samples: int,
    actor: str,
) -> TestRun:
    """Plan a test run on ``file_id``, or on ``samples`` varied files that would be re-encoded."""
    if not 1 <= samples <= MAX_SAMPLES:
        raise ValueError("samples out of range")
    profile = library_profile(session, library)
    if profile is None:
        raise NotApplicableError("no_profile")
    plans = {
        p.file_id: p
        for p in plan_library(db, library.id)
        if p.plan is not None and p.plan.action == "encode"
    }  # fmt: skip
    if file_id is not None:
        if file_id not in plans:
            raise NotApplicableError("not_an_encode_candidate")
        chosen = [file_id]
    else:
        if not plans:
            raise NotApplicableError("nothing_to_encode")
        library.test_run_samples = samples
        files = session.scalars(select(MediaFile).where(MediaFile.id.in_(list(plans)))).all()
        candidates = []
        for media_file in files:
            video = MediaInfo.model_validate(media_file.probe or {}).video
            height, hdr = (video.height, video.hdr) if video else (None, None)
            candidates.append(
                Candidate(media_file.id, media_file.size, media_file.title_id, height, hdr)
            )
        chosen = choose_samples(candidates, samples)

    run = TestRun(
        library_id=library.id,
        profile=profile.model_dump(),
        profile_fingerprint=profile_fingerprint(profile),
        requested_by=actor,
    )
    session.add(run)
    session.flush()
    for position, chosen_id in enumerate(chosen):
        sample_file = session.get(MediaFile, chosen_id)
        plan = plans[chosen_id].plan
        assert sample_file is not None and plan is not None  # noqa: S101
        sample = TestRunSample(
            test_run_id=run.id,
            media_file_id=sample_file.id,
            relative_path=sample_file.relative_path,
            position=position,
        )
        session.add(sample)
        session.flush()
        session.add(
            Job(
                library_id=library.id,
                media_file_id=sample_file.id,
                test_run_sample_id=sample.id,
                type="test",
                priority=10,  # ahead of bulk work: the owner is waiting for it
                source_path=sample_file.path,
                source_size=sample_file.size,
                source_mtime_ns=sample_file.mtime_ns,
                plan=plan.model_dump(mode="json"),
                probe=sample_file.probe or {},
                profile=profile.model_dump(),
                requested_by=actor,
            )
        )
    details = {"files": len(chosen), "profile": run.profile_fingerprint}
    audit.record(session, actor, "test_run.started", library.name, details)
    return run


def process_test(db: Database, settings: Settings, job_id: int, device: Device) -> None:
    with db.read() as session:
        job = session.get(Job, job_id)
        if job is None or job.test_run_sample_id is None or job.profile is None:
            return
        sample = session.get(TestRunSample, job.test_run_sample_id)
        run = session.get(TestRun, sample.test_run_id) if sample else None
        if sample is None or run is None:
            return
        source = Path(job.source_path)
        info = MediaInfo.model_validate(job.probe)
        plan = Plan.model_validate(job.plan)
        profile = ProfileSettings.model_validate(job.profile)
        snapshot = Snapshot(job.source_size, job.source_mtime_ns)
        sample_id, run_id, library_id = sample.id, run.id, run.library_id

    # Only the latest test run per library is kept on disk.
    library_dir = test_run_dir(settings, library_id)
    if library_dir.is_dir():
        for old in library_dir.iterdir():
            if old.name != str(run_id):
                remove_tree(old)
    folder = sample_dir(settings, library_id, run_id, sample_id)
    remove_tree(folder)
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

        run_encode(
            settings.ffmpeg,
            device,
            source,
            encoded,
            info,
            plan,
            profile,
            timeout_s=3600 + duration * 30,
            on_progress=progress,
            should_cancel=lambda: _is_cancelled(db, job_id),
            on_decoder=lambda decoder: _set(db, job_id, decoder=decoder),
        )
        _set(db, job_id, status="verifying", progress=0.8)
        target = expected_video(info, profile)
        new_info = verify_output(
            encoded, info, expected_encode_layout(source, info, plan, profile),
            settings.ffmpeg, settings.ffprobe, timeout_s=600 + duration, expected_video=target,
            expected_codecs=expected_codecs(source, info, plan, profile),
            expected_forced=expected_forced(source, info, plan, profile),
        )  # fmt: skip
        out_video = new_info.video
        assert out_video is not None and out_video.width is not None  # noqa: S101
        _set(db, job_id, progress=0.9)
        quality = measure(
            settings.ffmpeg, source, encoded, duration, out_video.width, target.height
        )
        size = still_size(info)
        hdr = info.video is not None and info.video.hdr in ("hdr10", "hlg")
        times: list[float] = []
        for at in frame_times(duration):
            # Numbered by the stills that worked, so times and pictures stay paired.
            if _stills(settings, source, encoded, folder, len(times), at, size, hdr):
                times.append(at)
        _set(db, job_id, progress=0.95)
        window = clip_window(duration)
        clip = _clips(settings, source, encoded, folder, window, size, hdr, device)
    except CancelledError:
        remove_tree(folder)
        _finish(db, job_id, sample_id, "failed", error="Cancelled.")
        return
    except Exception as exc:  # any failure must end the sample, never leave it "running"
        remove_tree(folder)
        _finish(db, job_id, sample_id, "failed", error=str(exc)[:2000] or exc.__class__.__name__)
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
        "clip": clip,
        "codec": out_video.codec,
        "height_before": info.video.height if info.video else None,
        "height_after": out_video.height,
        "bit_depth": out_video.bit_depth,
        "hdr": out_video.hdr,
        "device": device.id,
        "fps": stats.get("fps"),
        "seconds": round(time.monotonic() - started, 1),
    }
    _finish(db, job_id, sample_id, "done", result=result)


def frame_times(duration: float, count: int = STILLS) -> list[float]:
    """Moments for comparison stills, spread evenly through the video (10 % to 90 %)."""
    if duration <= 1:
        return [round(duration / 2, 2)]
    return [round(duration * (i + 1) / (count + 1), 2) for i in range(count)]


def clip_window(duration: float, seconds: float = CLIP_SECONDS) -> tuple[float, float]:
    """Start and length of the comparison clip: centred on the middle of the video, which
    is also the middle still."""
    if duration <= seconds:
        return 0.0, round(max(duration, 0.1), 2)
    return round(duration / 2 - seconds / 2, 2), seconds


def still_size(info: MediaInfo) -> tuple[int, int]:
    """The original's picture size (even, at most 4K wide): both stills are made at it."""
    video = info.video
    width, height = (video.width or 1280, video.height or 720) if video else (1280, 720)
    if width > MAX_STILL_WIDTH:
        width, height = MAX_STILL_WIDTH, round(height * MAX_STILL_WIDTH / width)
    return width - width % 2, height - height % 2


def _stills(
    settings: Settings,
    source: Path,
    encoded: Path,
    folder: Path,
    index: int,
    at: float,
    size: tuple[int, int],
    hdr: bool,
) -> bool:
    """Extract both stills for one moment; a failure only means no picture for it."""
    try:
        for which, video in (("source", source), ("encoded", encoded)):
            output = folder / f"frame-{index}-{which}.webp"
            extract_frame(settings.ffmpeg, video, at, output, size, hdr)
    except Exception:
        logger.warning("could not extract a comparison still", extra={"at": at})
        return False
    return True


def _clips(
    settings: Settings,
    source: Path,
    encoded: Path,
    folder: Path,
    window: tuple[float, float],
    size: tuple[int, int],
    hdr: bool,
    device: Device,
) -> dict[str, float] | None:
    """Both comparison clips; a failure only means there is nothing to play."""
    start, seconds = window
    try:
        for which, video in (("source", source), ("encoded", encoded)):
            output = folder / f"clip-{which}.mp4"
            extract_clip(settings.ffmpeg, video, start, seconds, output, size, hdr, device)
    except Exception:
        logger.warning("could not make the comparison clips", extra={"start": start})
        for which in ("source", "encoded"):
            (folder / f"clip-{which}.mp4").unlink(missing_ok=True)
        return None
    return {"start": start, "seconds": seconds}


def _finish(
    db: Database,
    job_id: int,
    sample_id: int,
    status: str,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    now = utcnow()
    with db.write() as session:
        sample = session.get(TestRunSample, sample_id)
        if sample is not None:
            sample.status = status
            sample.result = result
            sample.error = error
            sample.finished_at = now
        job = session.get(Job, job_id)
        if job is not None and status == "done":
            job.status = "done"
            job.progress = 1.0
            job.finished_at = now
        session.flush()
        run = session.get(TestRun, sample.test_run_id) if sample else None
        if run is not None:
            status_now = current_status(session, run)
            if status_now != "running":
                run.status = status_now
                run.finished_at = now


def approve(session: Session, run: TestRun, library: Library, actor: str) -> None:
    """The owner looked at the results and accepts the profile for bulk encoding."""
    if current_status(session, run) != "done":
        raise NotApplicableError("test_run_not_passed")
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
