"""Applying plans, the job queue and the recycle bin.

These are the only endpoints that lead to files being changed. Every change
goes through the verifier and the recycle bin, and is audit-logged.
"""

from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from reelhaven import audit
from reelhaven.api.deps import (
    AnyPrincipalDep,
    DbDep,
    InteractiveDep,
    csrf_protect,
    require_setup_done,
)
from reelhaven.api.schemas import StrictModel
from reelhaven.db import Job, JobResult, Library, MediaFile, RecycleItem
from reelhaven.db.types import utcnow
from reelhaven.dryrun import plan_library
from reelhaven.encode_planner import profile_fingerprint
from reelhaven.jobs.queue import JobQueue
from reelhaven.jobs.replace import ReplaceError
from reelhaven.jobs.service import (
    NotApplicableError,
    check_applicable,
    create_jobs,
    library_profile,
    purge_item,
    restore_item,
)
from reelhaven.live import eta_seconds

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])


def _queue(request: Request) -> JobQueue:
    queue: JobQueue = request.app.state.queue
    return queue


class JobOut(BaseModel):
    id: int
    library_id: int
    library_name: str | None
    media_file_id: int | None
    file: str
    type: str
    status: str
    progress: float
    summary: str
    details: list[str]
    error: str | None
    requested_by: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    bytes_before: int | None = None
    bytes_after: int | None = None
    process_seconds: float | None = None
    outcome: str | None = None
    device: str | None = None
    decoder: str | None = None  # "gpu" or "cpu" (ADR-0029)
    fps: float | None = None
    speed: float | None = None
    eta_seconds: int | None = None


class JobPage(BaseModel):
    total: int
    counts: dict[str, int]
    items: list[JobOut]


class ApplyLibrary(StrictModel):
    # The number of files the user saw and confirmed in the dry run. If the
    # library changed since, nothing is queued and the user must look again.
    expected_count: int = Field(ge=1)
    # Before a test run is approved (ADR-0020): queue only the files that need
    # track changes alone; files that will be re-encoded wait for approval.
    only_track_changes: bool = False


class ApplyResult(BaseModel):
    queued: int
    waiting: int = 0  # held back until their original language is known


class RecycleOut(BaseModel):
    id: int
    library_id: int
    original_path: str
    size: int
    reason: str
    job_id: int | None
    created_at: datetime
    expires_at: datetime
    restored_at: datetime | None
    purged_at: datetime | None


def job_out(job: Job, library: Library | None, result: JobResult | None) -> JobOut:
    root = Path(library.path) if library else None
    source = Path(job.source_path)
    shown = (
        source.relative_to(root).as_posix() if root and source.is_relative_to(root) else str(source)
    )
    return JobOut(
        id=job.id,
        library_id=job.library_id,
        library_name=library.name if library else None,
        media_file_id=job.media_file_id,
        file=shown,
        type=job.type,
        status=job.status,
        progress=job.progress,
        summary=str(job.plan.get("summary", "")),
        details=list(job.plan.get("details", [])),
        error=job.error,
        requested_by=job.requested_by,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        bytes_before=result.bytes_before if result else None,
        bytes_after=result.bytes_after if result else None,
        process_seconds=result.process_seconds if result else None,
        outcome=result.outcome if result else None,
        device=job.device,
        decoder=job.decoder,
        fps=job.fps or (result.fps if result else None),
        speed=job.speed,
        eta_seconds=(
            eta_seconds(job.progress, (utcnow() - job.started_at).total_seconds())
            if job.status in ("running", "verifying") and job.started_at is not None
            else None
        ),
    )


@router.post("/files/{file_id}/apply", status_code=status.HTTP_201_CREATED)
def apply_file(file_id: int, request: Request, db: DbDep, principal: InteractiveDep) -> JobOut:
    with db.read() as session:
        media_file = session.get(MediaFile, file_id)
        if media_file is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "file_not_found")
        library_id = media_file.library_id
    plans = [p for p in plan_library(db, library_id) if p.file_id == file_id]
    with db.write() as session:
        library = session.get(Library, library_id)
        media_file = session.get(MediaFile, file_id)
        assert library is not None and media_file is not None  # noqa: S101
        try:
            check_applicable(plans[0], media_file)
        except NotApplicableError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, exc.code) from exc
        jobs = create_jobs(session, library, plans, principal.actor)
        if not jobs:
            raise HTTPException(status.HTTP_409_CONFLICT, "already_queued")
        audit.record(
            session, principal.actor, "file.apply", media_file.relative_path, {"job": jobs[0].id}
        )
        out = job_out(jobs[0], library, None)
    _queue(request).notify()
    return out


@router.post("/libraries/{library_id}/apply")
def apply_library(
    library_id: int, body: ApplyLibrary, request: Request, db: DbDep, principal: InteractiveDep
) -> ApplyResult:
    try:
        plans = plan_library(db, library_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "library_not_found") from exc
    actions = ("remux",) if body.only_track_changes else ("remux", "encode")
    plans = [p for p in plans if p.plan is not None and p.plan.action in actions]
    changes = len(plans)
    if changes != body.expected_count:
        raise HTTPException(status.HTTP_409_CONFLICT, "plan_changed")
    encodes = any(p.plan is not None and p.plan.action == "encode" for p in plans)
    with db.write() as session:
        library = session.get(Library, library_id)
        assert library is not None  # noqa: S101
        profile = library_profile(session, library)
        if encodes and (
            profile is None or library.test_run_profile != profile_fingerprint(profile)
        ):
            # ADR-0020: a whole library is only encoded after a passed test run
            # with its current profile.
            raise HTTPException(status.HTTP_409_CONFLICT, "test_run_required")
        ready = [p for p in plans if not p.language_pending]
        jobs = create_jobs(session, library, ready, principal.actor)
        audit.record(session, principal.actor, "library.apply", library.name, {"queued": len(jobs)})
    _queue(request).notify()
    return ApplyResult(queued=len(jobs), waiting=len(plans) - len(ready))


@router.get("/jobs")
def list_jobs(
    db: DbDep,
    _principal: AnyPrincipalDep,
    status_filter: Literal["active", "failed", "done", "all"] = Query(
        default="all", alias="status"
    ),
    library_id: int | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> JobPage:
    query = (
        select(Job, Library, JobResult)
        .outerjoin(Library, Library.id == Job.library_id)
        .outerjoin(JobResult, JobResult.job_id == Job.id)
    )
    if library_id is not None:
        query = query.where(Job.library_id == library_id)
    if status_filter == "active":
        query = query.where(Job.status.in_(("queued", "running", "verifying")))
    elif status_filter == "failed":
        query = query.where(Job.status.in_(("failed", "cancelled")))
    elif status_filter == "done":
        query = query.where(Job.status == "done")
    with db.read() as session:
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = session.execute(query.order_by(Job.id.desc()).offset(offset).limit(limit)).all()
        counts = dict(session.execute(select(Job.status, func.count()).group_by(Job.status)).all())
        items = [job_out(job, library, result) for job, library, result in rows]
    return JobPage(total=total, counts=counts, items=items)


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: DbDep, _principal: AnyPrincipalDep) -> JobOut:
    with db.read() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "job_not_found")
        return job_out(job, session.get(Library, job.library_id), session.get(JobResult, job.id))


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, db: DbDep, principal: InteractiveDep) -> JobOut:
    with db.write() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "job_not_found")
        if job.status not in ("queued", "running", "verifying"):
            raise HTTPException(status.HTTP_409_CONFLICT, "job_not_active")
        job.status = "cancelled"
        if job.finished_at is None and job.started_at is None:
            job.finished_at = utcnow()
        audit.record(session, principal.actor, "job.cancelled", job.source_path, {"job": job_id})
        return job_out(job, session.get(Library, job.library_id), None)


@router.post("/jobs/{job_id}/retry", status_code=status.HTTP_201_CREATED)
def retry_job(job_id: int, request: Request, db: DbDep, principal: InteractiveDep) -> JobOut:
    """Plan the file again (it may have changed) and queue a new job."""
    with db.read() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "job_not_found")
        if job.status not in ("failed", "cancelled") or job.media_file_id is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "job_not_retryable")
        if job.type == "test":  # a retry would be a real encode; start a new test run instead
            raise HTTPException(status.HTTP_409_CONFLICT, "test_run_job")
        file_id = job.media_file_id
    return apply_file(file_id, request, db, principal)


@router.get("/recycle")
def list_recycle(
    db: DbDep,
    _principal: AnyPrincipalDep,
    library_id: int | None = None,
    show: Literal["active", "all"] = "active",
) -> list[RecycleOut]:
    query = select(RecycleItem)
    if library_id is not None:
        query = query.where(RecycleItem.library_id == library_id)
    if show == "active":
        query = query.where(RecycleItem.restored_at.is_(None), RecycleItem.purged_at.is_(None))
    with db.read() as session:
        return [
            RecycleOut.model_validate(item, from_attributes=True)
            for item in session.scalars(query.order_by(RecycleItem.id.desc()).limit(1000))
        ]


@router.post("/recycle/{item_id}/restore")
def restore_recycled(item_id: int, db: DbDep, principal: InteractiveDep) -> RecycleOut:
    try:
        item = restore_item(db, item_id, principal.actor)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ReplaceError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "restore_failed") from exc
    return RecycleOut.model_validate(item, from_attributes=True)


@router.delete("/recycle/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def purge_recycled(item_id: int, db: DbDep, principal: InteractiveDep) -> None:
    try:
        purge_item(db, item_id, principal.actor)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
