"""Downloadable reports to send when asking for help (ADR-0033)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse

from reelhaven import __version__, reports
from reelhaven.api.deps import AnyPrincipalDep, DbDep, csrf_protect, require_setup_done
from reelhaven.db.types import utcnow
from reelhaven.devices import DeviceRegistry

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])


def _devices(request: Request) -> list[str]:
    registry: DeviceRegistry | None = getattr(request.app.state, "devices", None)
    if registry is None:
        return []
    return [f"{r.name} ({r.family})" for r in registry.reports()]


def _download(text: str, name: str) -> PlainTextResponse:
    stamp = utcnow().strftime("%Y-%m-%d-%H%M")
    return PlainTextResponse(
        text,
        headers={"Content-Disposition": f'attachment; filename="reelhaven-{name}-{stamp}.txt"'},
    )


@router.get("/reports/failures", response_class=PlainTextResponse)
def failure_report(request: Request, db: DbDep, _principal: AnyPrincipalDep) -> PlainTextResponse:
    text = reports.failure_report(reports.failed_jobs(db), __version__, _devices(request), utcnow())
    return _download(text, "failures")
