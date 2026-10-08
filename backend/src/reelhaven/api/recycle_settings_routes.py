"""Recycle bin setting: how long originals are kept (ADR-0028)."""

from fastapi import APIRouter, Depends

from reelhaven import audit
from reelhaven.api.deps import (
    AnyPrincipalDep,
    DbDep,
    InteractiveDep,
    csrf_protect,
    require_setup_done,
)
from reelhaven.recycle_settings import RecycleSettings, load, save

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])


@router.get("/settings/recycle")
def get_recycle_settings(db: DbDep, _principal: AnyPrincipalDep) -> RecycleSettings:
    with db.read() as session:
        return load(session)


@router.put("/settings/recycle")
def put_recycle_settings(
    body: RecycleSettings, db: DbDep, principal: InteractiveDep
) -> RecycleSettings:
    """Applies to originals replaced from now on; items already in the bin keep their date."""
    with db.write() as session:
        before = load(session)
        save(session, body)
        if before.keep_days != body.keep_days:
            audit.record(
                session,
                principal.actor,
                "recycle.settings_changed",
                "recycle",
                {"keep_days": body.keep_days, "before": before.keep_days},
            )
    return body
