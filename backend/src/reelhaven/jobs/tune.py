"""Find my sweet spot (ADR-0031): one scene of one file encoded at several qualities, so
the owner can compare sizes and pictures and keep the smallest that still looks right.

Each step is its own job on a GPU. The scene is cut once, without re-encoding, and every
step encodes exactly that scene; the full-file size is estimated from how much smaller the
scene got. Originals are never touched.
"""

import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from reelhaven import audit
from reelhaven.config import Settings
from reelhaven.cpu_limit import preexec
from reelhaven.db import Database, Job, MediaFile, TuneSession, TuneStep
from reelhaven.db.types import utcnow
from reelhaven.encode_planner import VideoPlan, scaled_size, video_bitrate
from reelhaven.encoders import Device
from reelhaven.films import Film, FilmError, FilmLibrary, film
from reelhaven.jobs.encode_run import run_encode
from reelhaven.jobs.pipeline import JobFailedError, _is_cancelled, _set
from reelhaven.jobs.replace import Snapshot, check_unchanged, remove_tree
from reelhaven.jobs.runner import CancelledError, RunError
from reelhaven.jobs.test_run import clip_window, frame_times, make_clips, make_stills, still_size
from reelhaven.media.info import MediaInfo
from reelhaven.media.probe import ffmpeg_input, probe
from reelhaven.planner import Plan
from reelhaven.profiles import ProfileSettings
from reelhaven.quality_metrics import measure

logger = logging.getLogger(__name__)

# The three sizes a session starts with: the built-in High quality, Balanced and Small.
FIRST_STEPS = (8.0, 6.0, 4.0)
MAX_STEPS = 12
SCENE_SECONDS = 30.0
STEP_STILLS = 3
KEEP_SESSIONS = 3  # older sessions are removed, with their files, when a new one starts

_scene_locks: dict[int, threading.Lock] = {}
_scene_locks_guard = threading.Lock()


class TuneError(ValueError):
    """A request that can't be done; the message is the API's error code."""


def session_dir(settings: Settings, session_id: int) -> Path:
    return settings.transcode_dir / "tune" / str(session_id)


def step_dir(settings: Settings, session_id: int, step_id: int) -> Path:
    return session_dir(settings, session_id) / f"step-{step_id}"


def frame_path(settings: Settings, step: TuneStep, index: int, which: str) -> Path:
    return step_dir(settings, step.session_id, step.id) / f"frame-{index}-{which}.webp"


def clip_path(settings: Settings, step: TuneStep, which: str) -> Path:
    return step_dir(settings, step.session_id, step.id) / f"clip-{which}.mp4"


def scene_window(duration: float, seconds: float = SCENE_SECONDS) -> tuple[float, float]:
    """The scene every step encodes: ``seconds`` from 40 % into the film, past the opening
    and well before the credits; all of a short video."""
    if duration <= seconds:
        return 0.0, round(max(duration, 0.1), 2)
    return round(min(duration * 0.4, duration - seconds), 2), seconds


def estimate_size(
    file_bytes: int, video_bytes: int | None, scene_before: int, scene_after: int
) -> int:
    """The whole file's size after re-encoding, from how much smaller the scene got.

    Only the video changes, so the file keeps everything else and its video shrinks by the
    scene's ratio. Without a known video size, the whole file is scaled (an overestimate of
    the saving, but rare)."""
    ratio = scene_after / scene_before if scene_before > 0 else 1.0
    video = video_bytes if video_bytes is not None else file_bytes
    return max(int(file_bytes - video + video * ratio), 0)


def _video_plan(info: MediaInfo, profile: ProfileSettings) -> VideoPlan:
    video = info.video
    assert video is not None  # noqa: S101 - checked by the caller
    _width, height = scaled_size(video, profile)
    hdr = video.hdr in ("hdr10", "hlg")
    return VideoPlan(
        decision="encode",
        reason="Sweet-spot step.",
        codec=profile.codec,
        ten_bit=(profile.ten_bit or hdr) and profile.codec != "h264",
        height_before=video.height,
        height_after=height,
    )


def _check_source(info: MediaInfo, base: ProfileSettings) -> None:
    video = info.video
    if video is None or not video.width or not video.height:
        raise TuneError("no_video")
    if video.hdr in ("dolby_vision", "hdr10plus"):
        raise TuneError("hdr_not_reencoded")  # the planner never re-encodes these either
    if video.hdr in ("hdr10", "hlg") and base.codec == "h264":
        raise TuneError("hdr_not_in_h264")


@dataclass(frozen=True)
class Source:
    """What a session encodes: a library file or a downloaded test film."""

    label: str  # the library-relative path, or the film's title
    path: Path
    size: int
    mtime_ns: int
    probe: dict[str, Any]
    library_id: int | None = None
    media_file_id: int | None = None
    film_id: str | None = None


def library_source(media_file: MediaFile) -> Source:
    if media_file.status != "ok" or not media_file.probe:
        raise TuneError("file_not_read")
    return Source(
        label=media_file.relative_path,
        path=Path(media_file.path),
        size=media_file.size,
        mtime_ns=media_file.mtime_ns,
        probe=media_file.probe,
        library_id=media_file.library_id,
        media_file_id=media_file.id,
    )


def film_source(films: FilmLibrary, item: Film, ffprobe: str) -> Source:
    path = films.path(item)
    if films.state(item)[0] != "ready":
        raise TuneError("film_not_downloaded")
    st = path.stat()
    info = probe(path, ffprobe)
    return Source(
        label=item.title,
        path=path,
        size=st.st_size,
        mtime_ns=st.st_mtime_ns,
        probe=info.model_dump(mode="json"),
        film_id=item.id,
    )


def source_of(session: Session, films: FilmLibrary, ffprobe: str, tune: TuneSession) -> Source:
    """A session's source as it is now, for another step."""
    if tune.film_id is not None:
        try:
            return film_source(films, film(tune.film_id), ffprobe)
        except FilmError as exc:
            raise TuneError("film_gone") from exc
    media_file = session.get(MediaFile, tune.media_file_id) if tune.media_file_id else None
    if media_file is None:
        raise TuneError("file_gone")
    return library_source(media_file)


def _add_step(
    session: Session, tune: TuneSession, source: Source, quality: float, actor: str
) -> TuneStep:
    base = ProfileSettings.model_validate(tune.base)
    profile = base.model_copy(update={"quality": quality})
    ProfileSettings.model_validate(profile.model_dump())  # half steps from 1 to 10 only
    info = MediaInfo.model_validate(source.probe)
    step = TuneStep(session_id=tune.id, quality=quality)
    session.add(step)
    session.flush()
    plan = Plan(
        action="encode",
        tracks=[],
        flags=[],
        summary="Sweet-spot step",
        details=[
            f"Finding the sweet spot: quality {quality:g} on a {tune.scene_seconds:g}-second scene."
        ],
        removed_bytes=0,
        video=_video_plan(info, profile),
    )
    session.add(
        Job(
            library_id=source.library_id,
            media_file_id=source.media_file_id,
            tune_step_id=step.id,
            type="tune",
            priority=10,  # ahead of bulk work: the owner is waiting for it
            source_path=str(source.path),
            source_size=source.size,
            source_mtime_ns=source.mtime_ns,
            plan=plan.model_dump(mode="json"),
            probe=source.probe,
            profile=profile.model_dump(),
            requested_by=actor,
        )
    )
    return step


def create_session(
    session: Session,
    settings: Settings,
    source: Source,
    base: ProfileSettings,
    actor: str,
    qualities: tuple[float, ...] = FIRST_STEPS,
) -> TuneSession:
    """Start a session on ``source`` with a step per quality."""
    info = MediaInfo.model_validate(source.probe)
    _check_source(info, base)
    _remove_old_sessions(session, settings)
    start, seconds = scene_window(info.duration_s or 0.0)
    video = info.video
    assert video is not None  # noqa: S101 - _check_source
    bitrate = video_bitrate(info, video)
    tune = TuneSession(
        library_id=source.library_id,
        media_file_id=source.media_file_id,
        film_id=source.film_id,
        relative_path=source.label,
        base=base.model_dump(),
        scene_start=start,
        scene_seconds=seconds,
        file_bytes=source.size,
        video_bytes=(
            min(int(bitrate * info.duration_s / 8), source.size)
            if bitrate and info.duration_s
            else None
        ),
        requested_by=actor,
    )
    session.add(tune)
    session.flush()
    for quality in qualities:
        _add_step(session, tune, source, quality, actor)
    audit.record(session, actor, "tune.started", source.label, {"qualities": list(qualities)})
    return tune


def add_step(
    session: Session, tune: TuneSession, source: Source, quality: float, actor: str
) -> TuneStep:
    """Another step: a quality between, above or below the ones tried so far."""
    steps = session.scalars(select(TuneStep).where(TuneStep.session_id == tune.id)).all()
    if any(step.quality == quality for step in steps):
        raise TuneError("step_exists")
    if len(steps) >= MAX_STEPS:
        raise TuneError("too_many_steps")
    return _add_step(session, tune, source, quality, actor)


def is_running(session: Session, tune_id: int) -> bool:
    return (
        session.scalars(
            select(TuneStep.id).where(TuneStep.session_id == tune_id, TuneStep.status == "running")
        ).first()
        is not None
    )


def delete_session(session: Session, settings: Settings, tune: TuneSession) -> None:
    """Remove a session, its jobs and its files. Running steps are cancelled first."""
    step_ids = list(session.scalars(select(TuneStep.id).where(TuneStep.session_id == tune.id)))
    for job in session.scalars(select(Job).where(Job.tune_step_id.in_(step_ids))):
        if job.status in ("queued", "running", "verifying"):
            job.status = "cancelled"
            job.finished_at = utcnow()
    session.flush()
    # Children first, each flushed: the tables have no ORM relationships to order them.
    for job in session.scalars(select(Job).where(Job.tune_step_id.in_(step_ids))):
        session.delete(job)
    session.flush()
    for step in session.scalars(select(TuneStep).where(TuneStep.session_id == tune.id)):
        session.delete(step)
    session.flush()
    session.delete(tune)
    session.flush()
    remove_tree(session_dir(settings, tune.id))


def _remove_old_sessions(session: Session, settings: Settings) -> None:
    sessions = session.scalars(select(TuneSession).order_by(TuneSession.id.desc())).all()
    for old in sessions[KEEP_SESSIONS - 1 :]:
        if not is_running(session, old.id):
            delete_session(session, settings, old)


def _scene_lock(session_id: int) -> threading.Lock:
    with _scene_locks_guard:
        return _scene_locks.setdefault(session_id, threading.Lock())


def ensure_scene(
    settings: Settings, session_id: int, source: Path, start: float, seconds: float
) -> Path:
    """The session's scene, cut from the original without re-encoding (once, whichever
    step gets there first)."""
    scene = session_dir(settings, session_id) / "scene.mkv"
    with _scene_lock(session_id):
        if scene.is_file():
            return scene
        scene.parent.mkdir(parents=True, exist_ok=True)
        partial = scene.with_suffix(".part.mkv")
        args = [
            settings.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
            "-ss", f"{start:.3f}", "-i", ffmpeg_input(source), "-t", f"{seconds:.3f}",
            "-map", "0:v:0", "-c", "copy", "-an", "-sn", "-dn", "-y", ffmpeg_input(partial),
        ]  # fmt: skip
        subprocess.run(args, capture_output=True, timeout=600, check=True, preexec_fn=preexec())  # noqa: S603
        partial.rename(scene)
        return scene


def process_tune(db: Database, settings: Settings, job_id: int, device: Device) -> None:
    with db.read() as session:
        job = session.get(Job, job_id)
        if job is None or job.tune_step_id is None or job.profile is None:
            return
        step = session.get(TuneStep, job.tune_step_id)
        tune = session.get(TuneSession, step.session_id) if step else None
        if step is None or tune is None:
            return
        source = Path(job.source_path)
        plan = Plan.model_validate(job.plan)
        profile = ProfileSettings.model_validate(job.profile)
        snapshot = Snapshot(job.source_size, job.source_mtime_ns)
        step_id, tune_id = step.id, tune.id
        start, seconds = tune.scene_start, tune.scene_seconds
        file_bytes, video_bytes = tune.file_bytes, tune.video_bytes

    folder = step_dir(settings, tune_id, step_id)
    remove_tree(folder)
    folder.mkdir(parents=True)
    encoded = folder / "encoded.mkv"
    began = time.monotonic()
    stats: dict[str, float] = {}
    try:
        check_unchanged(source, snapshot)
        scene = ensure_scene(settings, tune_id, source, start, seconds)
        scene_info = probe(scene, settings.ffprobe)
        length = scene_info.duration_s or seconds

        def progress(fraction: float, fps: float | None = None, speed: float | None = None) -> None:
            if fps:
                stats["fps"] = fps
            _set(db, job_id, progress=round(fraction * 0.7, 3), fps=fps, speed=speed)

        run_encode(
            settings.ffmpeg,
            device,
            scene,
            encoded,
            scene_info,
            plan,
            profile,
            timeout_s=600 + length * 30,
            on_progress=progress,
            should_cancel=lambda: _is_cancelled(db, job_id),
            on_decoder=lambda decoder: _set(db, job_id, decoder=decoder),
        )
        _set(db, job_id, progress=0.75)
        out_video = probe(encoded, settings.ffprobe).video
        if out_video is None or not out_video.width or not out_video.height:
            raise ValueError("the encoded scene has no video")
        quality = measure(
            settings.ffmpeg, scene, encoded, length, out_video.width, out_video.height
        )
        _set(db, job_id, progress=0.9)
        size = still_size(scene_info)
        hdr = scene_info.video is not None and scene_info.video.hdr in ("hdr10", "hlg")
        times: list[float] = []
        for at in frame_times(length, STEP_STILLS):
            if make_stills(settings, scene, encoded, folder, len(times), at, size, hdr):
                times.append(at)
        clip = make_clips(settings, scene, encoded, folder, clip_window(length), size, hdr, device)
    except CancelledError:
        remove_tree(folder)
        _finish(db, job_id, step_id, "failed", error="Cancelled.")
        return
    except Exception as exc:  # any failure must end the step, never leave it "running"
        remove_tree(folder)
        _finish(db, job_id, step_id, "failed", error=str(exc)[:2000] or exc.__class__.__name__)
        if isinstance(exc, (RunError, OSError, ValueError, subprocess.SubprocessError)):
            raise JobFailedError(str(exc)) from exc
        raise

    scene_before, scene_after = scene.stat().st_size, encoded.stat().st_size
    estimate = estimate_size(file_bytes, video_bytes, scene_before, scene_after)
    result: dict[str, Any] = {
        "bytes_before": file_bytes,
        "bytes_after": estimate,
        "savings_percent": round(100 * (1 - estimate / file_bytes), 1) if file_bytes else None,
        "scene_bytes_before": scene_before,
        "scene_bytes_after": scene_after,
        "xpsnr": quality.xpsnr,
        "ssim": quality.ssim,
        "rating": quality.rating,
        "frame_times": times,
        "clip": clip,
        "codec": out_video.codec,
        "bit_depth": out_video.bit_depth,
        "height_after": out_video.height,
        "hdr": out_video.hdr,
        "device": device.id,
        "fps": stats.get("fps"),
        "seconds": round(time.monotonic() - began, 1),
    }
    encoded.unlink(missing_ok=True)  # the stills and clips are what's compared
    _finish(db, job_id, step_id, "done", result=result)


def _finish(
    db: Database,
    job_id: int,
    step_id: int,
    status: str,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    now = utcnow()
    with db.write() as session:
        step = session.get(TuneStep, step_id)
        if step is not None:
            step.status = status
            step.result = result
            step.error = error
            step.finished_at = now
        job = session.get(Job, job_id)
        if job is not None and status == "done":
            job.status = "done"
            job.progress = 1.0
            job.finished_at = now
