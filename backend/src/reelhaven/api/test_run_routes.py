"""Test runs: one trial encode per library, approved by the owner (ADR-0020)."""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi import Path as PathParam
from fastapi.responses import FileResponse
from pydantic import BaseModel

from reelhaven.api.deps import (
    AnyPrincipalDep,
    DbDep,
    InteractiveDep,
    csrf_protect,
    require_setup_done,
)
from reelhaven.api.schemas import StrictModel
from reelhaven.config import Settings
from reelhaven.db import Job, Library, MediaFile, TestRun
from reelhaven.encode_planner import profile_fingerprint
from reelhaven.jobs.service import NotApplicableError, library_profile
from reelhaven.jobs.test_run import approve, create_test_run, frame_path, latest

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])


class StartTestRun(StrictModel):
    file_id: int | None = None


class TestRunOut(BaseModel):
    __test__ = False

    id: int
    status: str
    file: str | None
    media_file_id: int | None
    profile: dict[str, Any]
    profile_is_current: bool
    result: dict[str, Any] | None
    error: str | None
    progress: float
    job_status: str | None
    fps: float | None
    created_at: datetime
    finished_at: datetime | None
    approved_by: str | None
    approved_at: datetime | None


def _out(session: Any, run: TestRun) -> TestRunOut:
    library = session.get(Library, run.library_id)
    media_file = session.get(MediaFile, run.media_file_id) if run.media_file_id else None
    job = session.query(Job).filter(Job.test_run_id == run.id).order_by(Job.id.desc()).first()
    profile = library_profile(session, library) if library else None
    return TestRunOut(
        id=run.id,
        status=run.status,
        file=media_file.relative_path if media_file else None,
        media_file_id=run.media_file_id,
        profile=run.profile,
        profile_is_current=profile is not None
        and profile_fingerprint(profile) == run.profile_fingerprint,
        result=run.result,
        error=run.error,
        progress=job.progress if job else 0.0,
        job_status=job.status if job else None,
        fps=job.fps if job else None,
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
        running = latest(session, library_id)
        if running is not None and running.status == "running":
            raise HTTPException(status.HTTP_409_CONFLICT, "test_run_in_progress")
        try:
            run = create_test_run(db, session, library, body.file_id, principal.actor)
        except NotApplicableError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, exc.code) from exc
        out = _out(session, run)
    request.app.state.queue.notify()
    return out


@router.get("/libraries/{library_id}/test-run")
def get_test_run(library_id: int, db: DbDep, _principal: AnyPrincipalDep) -> TestRunOut | None:
    with db.read() as session:
        if session.get(Library, library_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "library_not_found")
        run = latest(session, library_id)
        return None if run is None else _out(session, run)


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


@router.get("/test-runs/{run_id}/frames/{index}/{which}.jpg", include_in_schema=False)
def test_run_frame(
    run_id: int,
    request: Request,
    db: DbDep,
    _principal: AnyPrincipalDep,
    which: Literal["source", "encoded"],
    index: int = PathParam(ge=0, le=9),
) -> FileResponse:
    settings: Settings = request.app.state.settings
    with db.read() as session:
        run = session.get(TestRun, run_id)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "test_run_not_found")
        # Built only from integers and a fixed word: no user text reaches the path.
        path = frame_path(settings, run, index, which)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "frame_not_found")
    return FileResponse(
        path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"}
    )
