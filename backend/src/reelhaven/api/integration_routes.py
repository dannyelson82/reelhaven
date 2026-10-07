"""Sonarr, Radarr and TMDB connections. API keys go in, never come out."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from reelhaven import audit, settings_store
from reelhaven.api.deps import DbDep, InteractiveDep, csrf_protect, require_setup_done
from reelhaven.api.schemas import StrictModel
from reelhaven.db import Integration
from reelhaven.integrations.clients import TMDB_URL, IntegrationError, validate_base_url
from reelhaven.integrations.service import as_dict, make_client
from reelhaven.notify import NotifyStatus, status_key
from reelhaven.secretbox import SecretBox, SecretBoxError

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])

Kind = Literal["sonarr", "radarr", "tmdb", "plex"]


def get_box(request: Request) -> SecretBox:
    box: SecretBox = request.app.state.secretbox
    return box


BoxDep = Annotated[SecretBox, Depends(get_box)]


class PathMapping(StrictModel):
    remote: str = Field(min_length=1, max_length=4096)
    local: str = Field(min_length=1, max_length=4096)

    @field_validator("remote", "local")
    @classmethod
    def _absolute(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("/"):
            raise ValueError("paths must start with /")
        return value


class IntegrationOut(BaseModel):
    id: int
    kind: Kind
    name: str
    base_url: str
    verify_tls: bool
    path_mappings: list[PathMapping]
    enabled: bool
    api_key_hint: str
    last_notify: NotifyStatus | None = None  # Plex, Sonarr, Radarr (ADR-0025)


class IntegrationCreate(StrictModel):
    kind: Kind
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(default="", max_length=2048)
    api_key: str = Field(min_length=1, max_length=1024)
    verify_tls: bool = True
    path_mappings: list[PathMapping] = Field(default_factory=list, max_length=50)
    enabled: bool = True


class IntegrationUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = Field(default=None, min_length=1, max_length=1024)  # omit: keep
    verify_tls: bool | None = None
    path_mappings: list[PathMapping] | None = Field(default=None, max_length=50)
    enabled: bool | None = None


class TestRequest(StrictModel):
    kind: Kind
    base_url: str = Field(default="", max_length=2048)
    api_key: str | None = Field(default=None, max_length=1024)
    verify_tls: bool = True
    id: int | None = None  # use this integration's stored key when api_key is omitted


class TestResult(BaseModel):
    ok: bool
    app: str | None = None
    version: str | None = None
    error_code: str | None = None
    message: str | None = None


def _url(kind: str, base_url: str) -> str:
    if kind == "tmdb":
        return TMDB_URL
    try:
        return validate_base_url(base_url)
    except IntegrationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_url") from exc


def _get(session: object, integration_id: int) -> Integration:
    integration = session.get(Integration, integration_id)  # type: ignore[attr-defined]
    if integration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "integration_not_found")
    return integration  # type: ignore[no-any-return]


@router.get("/integrations")
def list_integrations(db: DbDep, box: BoxDep, _principal: InteractiveDep) -> list[IntegrationOut]:
    with db.read() as session:
        rows = session.scalars(select(Integration).order_by(Integration.kind, Integration.name))
        out = []
        for row in rows:
            raw = settings_store.get(session, status_key(row.id))
            last = NotifyStatus.model_validate(raw) if raw else None
            out.append(IntegrationOut(**as_dict(row, box), last_notify=last))
        return out


@router.post("/integrations", status_code=status.HTTP_201_CREATED)
def create_integration(
    body: IntegrationCreate, db: DbDep, box: BoxDep, principal: InteractiveDep
) -> IntegrationOut:
    integration = Integration(
        kind=body.kind,
        name=body.name.strip(),
        base_url=_url(body.kind, body.base_url),
        api_key_encrypted=box.encrypt(body.api_key.strip()),
        verify_tls=body.verify_tls,
        path_mappings=[m.model_dump() for m in body.path_mappings],
        enabled=body.enabled,
    )
    with db.write() as session:
        session.add(integration)
        try:
            session.flush()
        except IntegrityError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "name_taken") from exc
        audit.record(
            session,
            principal.actor,
            "integration.created",
            integration.name,
            {"kind": integration.kind, "base_url": integration.base_url},
        )
        return IntegrationOut(**as_dict(integration, box))


@router.patch("/integrations/{integration_id}")
def update_integration(
    integration_id: int,
    body: IntegrationUpdate,
    db: DbDep,
    box: BoxDep,
    principal: InteractiveDep,
) -> IntegrationOut:
    with db.write() as session:
        integration = _get(session, integration_id)
        changed: list[str] = []
        if body.name is not None:
            integration.name = body.name.strip()
            changed.append("name")
        if body.base_url is not None:
            integration.base_url = _url(integration.kind, body.base_url)
            changed.append("base_url")
        if body.api_key is not None:
            integration.api_key_encrypted = box.encrypt(body.api_key.strip())
            changed.append("api_key")
        if body.verify_tls is not None:
            integration.verify_tls = body.verify_tls
            changed.append("verify_tls")
        if body.path_mappings is not None:
            integration.path_mappings = [m.model_dump() for m in body.path_mappings]
            changed.append("path_mappings")
        if body.enabled is not None:
            integration.enabled = body.enabled
            changed.append("enabled")
        try:
            session.flush()
        except IntegrityError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "name_taken") from exc
        if changed:
            audit.record(
                session,
                principal.actor,
                "integration.updated",
                integration.name,
                {"fields": changed},
            )
        return IntegrationOut(**as_dict(integration, box))


@router.delete("/integrations/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration(integration_id: int, db: DbDep, principal: InteractiveDep) -> None:
    with db.write() as session:
        integration = _get(session, integration_id)
        session.delete(integration)
        audit.record(session, principal.actor, "integration.deleted", integration.name)


@router.post("/integrations/test")
def test_integration(
    body: TestRequest, request: Request, db: DbDep, box: BoxDep, _principal: InteractiveDep
) -> TestResult:
    """Try a connection with the settings in the form (saved or not)."""
    transport = request.app.state.http_transport
    base_url = body.base_url
    api_key = (body.api_key or "").strip()
    if not api_key and body.id is not None:
        with db.read() as session:
            stored = _get(session, body.id)
        base_url = base_url or stored.base_url
        try:
            api_key = box.decrypt(stored.api_key_encrypted)
        except SecretBoxError:
            return TestResult(
                ok=False, error_code="key_unreadable", message="Re-enter the API key and save"
            )
    if not api_key:
        return TestResult(ok=False, error_code="missing_key", message="Enter the API key")
    try:
        with make_client(
            body.kind, _url(body.kind, base_url), api_key, body.verify_tls, transport
        ) as client:
            info = client.test()
    except IntegrationError as exc:
        return TestResult(ok=False, error_code=exc.code, message=exc.message)
    return TestResult(ok=True, app=info["app"], version=info["version"])
