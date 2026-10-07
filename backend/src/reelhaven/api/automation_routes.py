"""Automation settings: pause, nightly rescan (ADR-0025)."""

from fastapi import APIRouter, Depends, Request

from reelhaven import audit
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
