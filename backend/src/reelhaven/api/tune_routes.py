"""Find my sweet spot (ADR-0031): sessions that encode one scene at several qualities."""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi import Path as PathParam
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from reelhaven.api.deps import (
    AnyPrincipalDep,
    DbDep,
    InteractiveDep,
    csrf_protect,
    require_setup_done,
)
from reelhaven.api.schemas import StrictModel
from reelhaven.config import Settings
from reelhaven.db import Job, MediaFile, TuneSession, TuneStep
from reelhaven.films import FilmError, film
from reelhaven.jobs.tune import (
    TuneError,
    add_step,
    clip_path,
    create_session,
    delete_session,
    film_source,
    frame_path,
    library_source,
    source_of,
)
from reelhaven.profiles import ProfileSettings

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])


class StartTune(StrictModel):
    # A library file or a downloaded test film (films.CATALOGUE id): exactly one.
    file_id: int | None = None
    film_id: str | None = Field(default=None, max_length=64)
    # Codec, speed, 10-bit, resolution and audio every step shares; quality is per step.
    settings: ProfileSettings


class AddStep(StrictModel):
    quality: float = Field(ge=1, le=10, multiple_of=0.5)


class TuneStepOut(BaseModel):
    id: int
    quality: float
    status: str  # queued | running | done | failed
    result: dict[str, Any] | None
    error: str | None
    progress: float
    job_id: int | None
    fps: float | None


class TuneSessionOut(BaseModel):
    id: int
    file: str
    media_file_id: int | None
    library_id: int | None
    film_id: str | None
    base: ProfileSettings
    scene_start: float
    scene_seconds: float
    file_bytes: int
    steps: list[TuneStepOut]  # best quality first
    created_at: datetime


def _step_out(step: TuneStep, job: Job | None) -> TuneStepOut:
    status_now = step.status
    if status_now == "running" and job is not None:
        if job.status == "queued":
            status_now = "queued"
        elif job.status in ("failed", "cancelled"):
            status_now = "failed"  # the job ended before the step could record it
    return TuneStepOut(
        id=step.id,
        quality=step.quality,
        status=status_now,
        result=step.result,
        error=step.error
        or (job.error if job and status_now == "failed" else None)
        or ("Cancelled." if job and job.status == "cancelled" else None),
        progress=1.0 if step.status == "done" else job.progress if job else 0.0,
        job_id=job.id if job else None,
        fps=job.fps if job else None,
    )


def _out(session: Session, tune: TuneSession) -> TuneSessionOut:
    steps = session.scalars(
        select(TuneStep).where(TuneStep.session_id == tune.id).order_by(TuneStep.quality.desc())
    ).all()
    jobs = {
        job.tune_step_id: job
        for job in session.scalars(
            select(Job).where(Job.tune_step_id.in_([step.id for step in steps]))
        )
    }
    return TuneSessionOut(
        id=tune.id,
        file=tune.relative_path,
        media_file_id=tune.media_file_id,
        library_id=tune.library_id,
        film_id=tune.film_id,
        base=ProfileSettings.model_validate(tune.base),
        scene_start=tune.scene_start,
        scene_seconds=tune.scene_seconds,
        file_bytes=tune.file_bytes,
        steps=[_step_out(step, jobs.get(step.id)) for step in steps],
        created_at=tune.created_at,
    )


def _session(session: Session, session_id: int) -> TuneSession:
    tune = session.get(TuneSession, session_id)
    if tune is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tune_session_not_found")
    return tune


@router.post("/tune-sessions", status_code=status.HTTP_201_CREATED)
def start_tune(
    body: StartTune, request: Request, db: DbDep, principal: InteractiveDep
) -> TuneSessionOut:
    settings: Settings = request.app.state.settings
    if (body.file_id is None) == (body.film_id is None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "file_or_film")
    try:
        # A film is probed here, outside the database's write lock.
        film_src = (
            film_source(request.app.state.films, film(body.film_id), settings.ffprobe)
            if body.film_id is not None
            else None
        )
    except FilmError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except TuneError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    with db.write() as session:
        try:
            if film_src is not None:
                source = film_src
            else:
                media_file = session.get(MediaFile, body.file_id)
                if media_file is None:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, "file_not_found")
                source = library_source(media_file)
            tune = create_session(session, settings, source, body.settings, principal.actor)
        except TuneError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        session.flush()
        out = _out(session, tune)
    request.app.state.queue.notify()
    return out


@router.get("/tune-sessions")
def list_tunes(db: DbDep, _principal: AnyPrincipalDep) -> list[TuneSessionOut]:
    """The kept sessions, newest first."""
    with db.read() as session:
        tunes = session.scalars(select(TuneSession).order_by(TuneSession.id.desc())).all()
        return [_out(session, tune) for tune in tunes]


@router.get("/tune-sessions/{session_id}")
def get_tune(session_id: int, db: DbDep, _principal: AnyPrincipalDep) -> TuneSessionOut:
    with db.read() as session:
        return _out(session, _session(session, session_id))


@router.post("/tune-sessions/{session_id}/steps", status_code=status.HTTP_201_CREATED)
def add_tune_step(
    session_id: int, body: AddStep, request: Request, db: DbDep, principal: InteractiveDep
) -> TuneSessionOut:
    settings: Settings = request.app.state.settings
    try:
        with db.read() as session:
            tune = _session(session, session_id)
            film_id = tune.film_id
        # A film is probed here, outside the database's write lock.
        film_src = (
            film_source(request.app.state.films, film(film_id), settings.ffprobe)
            if film_id is not None
            else None
        )
    except (FilmError, TuneError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "film_gone") from exc
    with db.write() as session:
        tune = _session(session, session_id)
        try:
            source = film_src or source_of(session, request.app.state.films, settings.ffprobe, tune)
            add_step(session, tune, source, body.quality, principal.actor)
        except TuneError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        session.flush()
        out = _out(session, tune)
    request.app.state.queue.notify()
    return out


@router.delete("/tune-sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tune(session_id: int, request: Request, db: DbDep, _principal: InteractiveDep) -> None:
    with db.write() as session:
        delete_session(session, request.app.state.settings, _session(session, session_id))


def _step(session: Session, step_id: int) -> TuneStep:
    step = session.get(TuneStep, step_id)
    if step is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tune_step_not_found")
    return step


@router.get("/tune-steps/{step_id}/frames/{index}/{which}", include_in_schema=False)
def tune_frame(
    step_id: int,
    request: Request,
    db: DbDep,
    _principal: AnyPrincipalDep,
    which: Literal["source", "encoded"],
    index: int = PathParam(ge=0, le=9),
) -> FileResponse:
    with db.read() as session:
        # Built only from integers and a fixed word: no user text reaches the path.
        path = frame_path(request.app.state.settings, _step(session, step_id), index, which)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "frame_not_found")
    return FileResponse(
        path, media_type="image/webp", headers={"Cache-Control": "private, max-age=3600"}
    )


@router.get("/tune-steps/{step_id}/clips/{which}", include_in_schema=False)
def tune_clip(
    step_id: int,
    request: Request,
    db: DbDep,
    _principal: AnyPrincipalDep,
    which: Literal["source", "encoded"],
) -> FileResponse:
    with db.read() as session:
        path = clip_path(request.app.state.settings, _step(session, step_id), which)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "clip_not_found")
    return FileResponse(
        path, media_type="video/mp4", headers={"Cache-Control": "private, max-age=3600"}
    )
