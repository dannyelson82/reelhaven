"""Encode devices: what was detected, test results, and their settings."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from reelhaven import audit, cpu_limit, device_settings
from reelhaven.api.deps import (
    AnyPrincipalDep,
    DbDep,
    InteractiveDep,
    csrf_protect,
    require_setup_done,
)
from reelhaven.device_settings import DeviceSettings
from reelhaven.devices import DeviceRegistry

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])


class CodecResultOut(BaseModel):
    codec: str
    ten_bit: bool
    encoder: str
    ok: bool
    error: str | None
    seconds: float | None


class DeviceOut(BaseModel):
    id: str
    kind: str
    name: str
    family: str
    results: list[CodecResultOut]
    enabled: bool
    concurrency: int


class DevicesOut(BaseModel):
    detecting: bool
    detected_at: float | None
    devices: list[DeviceOut]
    settings: DeviceSettings
    cpu_cores_available: int  # cores this container may use


def _registry(request: Request) -> DeviceRegistry:
    registry: DeviceRegistry = request.app.state.devices
    return registry


def _out(request: Request, db: DbDep) -> DevicesOut:
    registry = _registry(request)
    with db.read() as session:
        settings = device_settings.load(session)
    devices = []
    for report in registry.reports():
        config = settings.config_for(report.id)
        enabled = settings.cpu_enabled if report.kind == "cpu" else config.enabled
        concurrency = settings.cpu_concurrency if report.kind == "cpu" else config.concurrency
        devices.append(
            DeviceOut(
                id=report.id, kind=report.kind, name=report.name, family=report.family,
                results=[CodecResultOut(**vars(r)) for r in report.results],
                enabled=enabled, concurrency=concurrency,
            )
        )  # fmt: skip
    return DevicesOut(
        detecting=registry.detecting, detected_at=registry.detected_at, devices=devices,
        settings=settings, cpu_cores_available=len(cpu_limit.available()),
    )  # fmt: skip


@router.get("/devices")
def get_devices(request: Request, db: DbDep, _principal: AnyPrincipalDep) -> DevicesOut:
    return _out(request, db)


@router.post("/devices/detect", status_code=202)
def detect_devices(request: Request, db: DbDep, _principal: InteractiveDep) -> DevicesOut:
    _registry(request).detect_in_background()
    return _out(request, db)


@router.put("/devices/settings")
def put_device_settings(
    body: DeviceSettings, request: Request, db: DbDep, principal: InteractiveDep
) -> DevicesOut:
    with db.write() as session:
        device_settings.save(session, body)
        audit.record(session, principal.actor, "devices.updated", None, body.model_dump())
    cpu_limit.set_limit(body.cpu_cores)  # applies to every process started from now on
    return _out(request, db)
