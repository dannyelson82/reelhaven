"""Space saved over the life of the install (ADR-0026)."""

from dataclasses import asdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from reelhaven.api.deps import AnyPrincipalDep, DbDep, csrf_protect, require_setup_done
from reelhaven.db import Job, JobResult, Library, RecycleItem
from reelhaven.db.types import utcnow
from reelhaven.device_stats import JobRow, daily, device_stats
from reelhaven.savings import Event, Period, summarise

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])


class LibrarySavingsOut(BaseModel):
    library_id: int
    name: str
    saved: int
    files: int


class SavingsOut(BaseModel):
    total_saved: int
    files: int
    this_week: int
    this_month: int
    weekly: list[Period]
    monthly: list[Period]
    libraries: list[LibrarySavingsOut]


def _local(moment: datetime) -> datetime:
    """Stored times are UTC; weeks and months follow the server's clock (TZ)."""
    return moment.astimezone().replace(tzinfo=None)


@router.get("/stats/savings")
def savings(db: DbDep, _principal: AnyPrincipalDep) -> SavingsOut:
    events: list[Event] = []
    with db.read() as session:
        credited: dict[int, int] = {}
        for result, job in session.execute(
            select(JobResult, Job)
            .join(Job, Job.id == JobResult.job_id)
            .where(JobResult.outcome == "replaced", Job.finished_at.is_not(None))
        ):
            saved = result.bytes_before - result.bytes_after
            credited[job.id] = saved
            assert job.finished_at is not None and job.library_id is not None  # noqa: S101
            events.append(Event(_local(job.finished_at), job.library_id, saved, 1))
        items = list(session.scalars(select(RecycleItem)))
        swaps = {(i.original_path, i.created_at): i for i in items if i.reason == "restore-swap"}
        for item in items:
            if item.restored_at is None:
                continue
            when = _local(item.restored_at)
            if item.reason == "replaced" and item.job_id in credited:
                # The original is back: that job's saving is gone.
                events.append(Event(when, item.library_id, -credited[item.job_id], -1))
            elif item.reason == "restore-swap":
                # ReelHaven's version is back: the space comes back too.
                displaced = swaps.get((item.original_path, item.restored_at))
                if displaced is not None:
                    events.append(Event(when, item.library_id, displaced.size - item.size, 1))
        names = {lib.id: lib.name for lib in session.scalars(select(Library))}
    s = summarise(events, datetime.now())  # noqa: DTZ005 - local wall-clock time on purpose
    return SavingsOut(
        total_saved=s.total_saved,
        files=s.files,
        this_week=s.this_week,
        this_month=s.this_month,
        weekly=s.weekly,
        monthly=s.monthly,
        libraries=[
            LibrarySavingsOut(
                library_id=lib.library_id,
                name=names.get(lib.library_id, "Removed library"),
                saved=lib.saved,
                files=lib.files,
            )
            for lib in s.libraries
        ],
    )


class DeviceStatsOut(BaseModel):
    device: str
    files: int
    failed: int
    saved: int
    video_hours: float
    work_hours: float
    speed: float | None
    fps: float | None
    gpu_decoded: float | None


class DayOut(BaseModel):
    day: date
    encoded: int
    remuxed: int
    failed: int
    saved: int


class PerformanceOut(BaseModel):
    devices: list[DeviceStatsOut]
    daily: list[DayOut]


@router.get("/stats/performance")
def performance(
    db: DbDep,
    _principal: AnyPrincipalDep,
    days: int = Query(default=30, ge=0, le=3650),
) -> PerformanceOut:
    """Per-device encodes over the last ``days`` days (0: all time), and jobs per day."""
    with db.read() as session:
        rows = [
            JobRow(
                finished=_local(job.finished_at),
                type=job.type,
                status=job.status,
                device=job.device,
                decoder=job.decoder,
                outcome=result.outcome if result else None,
                saved=(result.bytes_before - result.bytes_after)
                if result and result.outcome == "replaced"
                else 0,
                video_seconds=result.duration_s if result else None,
                work_seconds=result.process_seconds if result else None,
                fps=result.fps if result else None,
            )
            for job, result in session.execute(
                select(Job, JobResult)
                .outerjoin(JobResult, JobResult.job_id == Job.id)
                .where(Job.finished_at.is_not(None), Job.type.in_(("encode", "remux")))
            )
            if job.finished_at is not None
        ]
    now = _local(utcnow())
    since = now - timedelta(days=days) if days else None
    return PerformanceOut(
        devices=[DeviceStatsOut(**asdict(d)) for d in device_stats(rows, since)],
        daily=[DayOut(**asdict(d)) for d in daily(rows, now.date())],
    )
