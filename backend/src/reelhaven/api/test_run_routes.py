"""Test runs: trial encodes of a few files per library, approved by the owner (ADR-0020)."""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi import Path as PathParam
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
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
from reelhaven.db import Library, TestRun, TestRunSample
from reelhaven.encode_planner import profile_fingerprint
from reelhaven.jobs.service import NotApplicableError, library_profile
from reelhaven.jobs.test_run import (
    approve,
    clip_path,
    create_test_run,
    frame_path,
    latest,
    run_status,
    sample_status,
    samples_of,
)
from reelhaven.sampling import MAX_SAMPLES

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])


class StartTestRun(StrictModel):
    file_id: int | None = None
    samples: int = Field(default=1, ge=1, le=MAX_SAMPLES)


class TestSampleOut(BaseModel):
    __test__ = False

    id: int
    file: str
    media_file_id: int | None
    status: str
    result: dict[str, Any] | None
    error: str | None
    progress: float
    job_id: int | None
    job_status: str | None
    fps: float | None


class TestRunOut(BaseModel):
    __test__ = False

    id: int
    status: str
    profile: dict[str, Any]
    profile_is_current: bool
    samples: list[TestSampleOut]
    created_at: datetime
    finished_at: datetime | None
    approved_by: str | None
    approved_at: datetime | None


class TestRunState(BaseModel):
    """The library's sample count and its latest test run, if any."""

    samples: int
    run: TestRunOut | None


def _out(session: Session, run: TestRun) -> TestRunOut:
    library = session.get(Library, run.library_id)
    profile = library_profile(session, library) if library else None
    samples = [
        TestSampleOut(
            id=sample.id,
            file=sample.relative_path,
            media_file_id=sample.media_file_id,
            status=sample_status(sample, job.status if job else None),
            result=sample.result,
            error=sample.error
            or (job.error if job else None)
            or ("Cancelled." if job and job.status == "cancelled" else None),
            progress=1.0 if sample.status == "done" else job.progress if job else 0.0,
            job_id=job.id if job else None,
            job_status=job.status if job else None,
            fps=job.fps if job else None,
        )
        for sample, job in samples_of(session, run)
    ]
    return TestRunOut(
        id=run.id,
        status=run_status(run, (s.status for s in samples)),
        profile=run.profile,
        profile_is_current=profile is not None
        and profile_fingerprint(profile) == run.profile_fingerprint,
        samples=samples,
        created_at=run.created_at,
        finished_at=run.finished_at,
        approved_by=run.approved_by,
        approved_at=run.approved_at,
    )


@router.post("/libraries/{library_id}/test-run", status_code=status.HTTP_201_CREATED)
def start_test_run(
    library_id: int, body: StartTestRun, request: Request, db: DbDep, principal: InteractiveDep
) -> TestRunOut:
    with db.write() as session:
        library = session.get(Library, library_id)
        if library is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "library_not_found")
        previous = latest(session, library_id)
        if previous is not None and _out(session, previous).status == "running":
            raise HTTPException(status.HTTP_409_CONFLICT, "test_run_in_progress")
        try:
            run = create_test_run(db, session, library, body.file_id, body.samples, principal.actor)
        except NotApplicableError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, exc.code) from exc
        session.flush()
        out = _out(session, run)
    request.app.state.queue.notify()
    return out


@router.get("/libraries/{library_id}/test-run")
def get_test_run(library_id: int, db: DbDep, _principal: AnyPrincipalDep) -> TestRunState:
    with db.read() as session:
        library = session.get(Library, library_id)
        if library is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "library_not_found")
        run = latest(session, library_id)
        return TestRunState(
            samples=library.test_run_samples, run=None if run is None else _out(session, run)
        )


@router.post("/test-runs/{run_id}/approve")
def approve_test_run(run_id: int, db: DbDep, principal: InteractiveDep) -> TestRunOut:
    with db.write() as session:
        run = session.get(TestRun, run_id)
        library = session.get(Library, run.library_id) if run else None
        if run is None or library is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "test_run_not_found")
        try:
            approve(session, run, library, principal.actor)
        except NotApplicableError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, exc.code) from exc
        return _out(session, run)


@router.get("/test-run-samples/{sample_id}/clips/{which}", include_in_schema=False)
def test_run_clip(
    sample_id: int,
    request: Request,
    db: DbDep,
    _principal: AnyPrincipalDep,
    which: Literal["source", "encoded"],
) -> FileResponse:
    """A comparison clip; the browser seeks in it with range requests."""
    settings: Settings = request.app.state.settings
    with db.read() as session:
        sample = session.get(TestRunSample, sample_id)
        run = session.get(TestRun, sample.test_run_id) if sample else None
        if sample is None or run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "test_run_not_found")
        # Built only from integers and a fixed word: no user text reaches the path.
        path = clip_path(settings, run, sample.id, which)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "clip_not_found")
    return FileResponse(
        path, media_type="video/mp4", headers={"Cache-Control": "private, max-age=3600"}
    )


@router.get("/test-run-samples/{sample_id}/frames/{index}/{which}", include_in_schema=False)
def test_run_frame(
    sample_id: int,
    request: Request,
    db: DbDep,
    _principal: AnyPrincipalDep,
    which: Literal["source", "encoded"],
    index: int = PathParam(ge=0, le=9),
) -> FileResponse:
    settings: Settings = request.app.state.settings
    with db.read() as session:
        sample = session.get(TestRunSample, sample_id)
        run = session.get(TestRun, sample.test_run_id) if sample else None
        if sample is None or run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "test_run_not_found")
        # Built only from integers and a fixed word: no user text reaches the path.
        path = frame_path(settings, run, sample.id, index, which)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "frame_not_found")
    media_type = "image/webp" if path.suffix == ".webp" else "image/jpeg"
    return FileResponse(
        path, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"}
    )
