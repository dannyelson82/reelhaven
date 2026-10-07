"""Setup wizard state (ADR-0026): what the first-run flow has already done."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from reelhaven import settings_store
from reelhaven.api.deps import (
    AnyPrincipalDep,
    DbDep,
    InteractiveDep,
    csrf_protect,
    require_setup_done,
)

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])
KEY = "onboarding"


class Onboarding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wizard_seen: bool = False  # the first-run wizard opened once (finished or dismissed)
    server_steps_done: bool = False  # hardware + apps steps; later runs skip them


@router.get("/onboarding")
def get_onboarding(db: DbDep, _principal: AnyPrincipalDep) -> Onboarding:
    with db.read() as session:
        raw = settings_store.get(session, KEY)
        return Onboarding() if raw is None else Onboarding.model_validate(raw)


@router.put("/onboarding")
def put_onboarding(body: Onboarding, db: DbDep, _principal: InteractiveDep) -> Onboarding:
    with db.write() as session:
        settings_store.put(session, KEY, body.model_dump())
    return body
