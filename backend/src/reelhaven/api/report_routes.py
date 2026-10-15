"""Downloadable reports to send when asking for help, and the Developer options switch
that shows their buttons (ADR-0033)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse

from reelhaven import __version__, developer_settings, reports, review_log
from reelhaven.api.deps import (
    AnyPrincipalDep,
    DbDep,
    InteractiveDep,
    csrf_protect,
    require_setup_done,
)
from reelhaven.api.review_routes import current_items
from reelhaven.db.types import utcnow
from reelhaven.developer_settings import DeveloperSettings
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


@router.get("/settings/developer")
def get_developer_settings(db: DbDep, _principal: AnyPrincipalDep) -> DeveloperSettings:
    with db.read() as session:
        return developer_settings.load(session)


@router.put("/settings/developer")
def put_developer_settings(
    body: DeveloperSettings, db: DbDep, _principal: InteractiveDep
) -> DeveloperSettings:
    with db.write() as session:
        developer_settings.save(session, body)
    return body


@router.get("/reports/review", response_class=PlainTextResponse)
def review_report(request: Request, db: DbDep, _principal: AnyPrincipalDep) -> PlainTextResponse:
    current = reports.review_facts(db, current_items(db))
    resolved = [
        reports.ResolvedEntry(
            r.library_name, r.relative_path, r.kind, r.detail, r.first_seen_at, r.resolved_at
        )
        for r in review_log.resolved_since(db)
        if r.resolved_at is not None
    ]
    text = reports.review_report(current, resolved, __version__, _devices(request), utcnow())
    return _download(text, "review")
