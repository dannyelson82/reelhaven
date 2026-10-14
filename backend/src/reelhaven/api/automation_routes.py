"""Automation settings: pause, nightly rescan (ADR-0025); the hold while a disk is full."""

from datetime import datetime

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel

from reelhaven import audit, space_hold
from reelhaven.api.deps import (
    AnyPrincipalDep,
    DbDep,
    InteractiveDep,
    csrf_protect,
    require_setup_done,
)
from reelhaven.automation_settings import AutomationSettings, load, save

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])


@router.get("/automation")
def get_automation(db: DbDep, _principal: AnyPrincipalDep) -> AutomationSettings:
    with db.read() as session:
        return load(session)


@router.put("/automation")
def put_automation(
    body: AutomationSettings, request: Request, db: DbDep, principal: InteractiveDep
) -> AutomationSettings:
    with db.write() as session:
        before = load(session)
        save(session, body)
        changes = {k: v for k, v in body.model_dump().items() if getattr(before, k) != v}
        if changes:
            audit.record(session, principal.actor, "automation.updated", "automation", changes)
    if before.paused and not body.paused:
        request.app.state.queue.notify()
        request.app.state.automation.poke()
    return body


# --- stopped because a disk is full ----------------------------------------------------


class DiskOut(BaseModel):
    path: str
    free_bytes: int


class SpaceHoldOut(BaseModel):
    since: datetime
    error: str
    needed_bytes: int
    disks: list[DiskOut]


def _space_out(db: DbDep) -> SpaceHoldOut | None:
    with db.read() as session:
        hold = space_hold.load(session)
    if hold is None:
        return None
    free = space_hold.free_space(hold.paths)
    return SpaceHoldOut(
        since=hold.since,
        error=hold.error,
        needed_bytes=hold.needed_bytes,
        disks=[DiskOut(path=p, free_bytes=free[p]) for p in hold.paths],
    )


@router.get("/automation/space-hold")
def get_space_hold(db: DbDep, _principal: AnyPrincipalDep) -> SpaceHoldOut | None:
    return _space_out(db)


@router.post("/automation/space-hold/check")
def check_space_hold(
    request: Request, db: DbDep, _principal: InteractiveDep
) -> SpaceHoldOut | None:
    """Measure the disks now instead of waiting for the next check."""
    request.app.state.queue.space_held(check_now=True)
    return _space_out(db)


@router.delete("/automation/space-hold", status_code=status.HTTP_204_NO_CONTENT)
def resume_anyway(request: Request, db: DbDep, principal: InteractiveDep) -> None:
    """Carry on without waiting for the free space ReelHaven asked for."""
    with db.write() as session:
        if space_hold.clear(session):
            audit.record(session, principal.actor, "queue.disk_hold_lifted", "automation")
    request.app.state.queue.notify()
