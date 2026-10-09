"""Sonarr/Radarr webhooks (ADR-0025): a file was imported, upgraded, renamed or deleted.

Authenticated with the API key (``?apikey=`` in the URL Sonarr/Radarr call, or
the X-Api-Key header). The library is rescanned through the folder watcher, so
the same settle and follow-up rules apply; Automatic libraries then process
the new files.
"""

import json
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from reelhaven import audit, settings_store
from reelhaven.api.deps import AnyPrincipalDep, DbDep, csrf_protect, require_setup_done
from reelhaven.db import Integration, Library
from reelhaven.db.types import utcnow
from reelhaven.watcher import title_folder
from reelhaven.webhooks import CHANGE_EVENTS, Kind, match_library, remote_paths

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])

MAX_BODY = 1024 * 1024
Outcome = Literal["test", "rescan", "not_watched", "no_library", "ignored"]


class WebhookResult(BaseModel):
    outcome: Outcome
    message: str
    library: str | None = None


class WebhookLast(BaseModel):
    at: datetime
    event: str
    outcome: Outcome
    message: str
    library: str | None = None
    path: str | None = None


def _status_key(kind: Kind) -> str:
    return f"webhook_last_{kind}"


@router.post("/webhook/{kind}")
async def webhook(
    kind: Kind, request: Request, db: DbDep, principal: AnyPrincipalDep
) -> WebhookResult:
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "payload_too_large")
    try:
        payload: Any = json.loads(body or b"{}")
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_json") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_payload")
    event = str(payload.get("eventType", ""))[:64] or "unknown"
    name = "Sonarr" if kind == "sonarr" else "Radarr"
    library_name: str | None = None
    local: str | None = None

    if event == "Test":
        result = WebhookResult(outcome="test", message=f"{name} can reach ReelHaven.")
    elif event not in CHANGE_EVENTS:
        result = WebhookResult(outcome="ignored", message=f"{event} events don't change files.")
    else:
        with db.read() as session:
            mappings = [
                i.path_mappings
                for i in session.scalars(
                    select(Integration).where(Integration.kind == kind, Integration.enabled)
                )
            ]
            libraries = {lib.id: lib for lib in session.scalars(select(Library))}
        match = match_library(
            remote_paths(kind, payload),
            mappings,
            [(lib.id, lib.path) for lib in libraries.values()],
        )
        if match is None:
            result = WebhookResult(
                outcome="no_library",
                message=f"The path {name} sent isn't in any library. Check the path mappings.",
            )
        else:
            library = libraries[match[0]]
            library_name, local = library.name, match[1]
            if library.watch_mode == "off":
                result = WebhookResult(
                    outcome="not_watched",
                    message=f"{library.name} is set to Off, so nothing happens on its own.",
                    library=library.name,
                )
            else:
                # Sonarr/Radarr name the series or film folder (or a file in it): only that
                # folder is rescanned (ADR-0030). Such a path is a folder, even if it's gone.
                folder = title_folder(library.path, local, is_directory=True)
                request.app.state.watcher.changed(library.id, folder)
                where = library.name if folder is None else f"{folder} in {library.name}"
                result = WebhookResult(
                    outcome="rescan",
                    message=f"{where} will be rescanned shortly.",
                    library=library.name,
                )

    last = WebhookLast(
        at=utcnow(),
        event=event,
        outcome=result.outcome,
        message=result.message,
        library=library_name,
        path=local,
    )
    with db.write() as session:
        settings_store.put(session, _status_key(kind), last.model_dump(mode="json"))
        if result.outcome == "rescan":
            audit.record(
                session,
                principal.actor,
                f"webhook.{kind}",
                library_name,
                {"event": event, "path": local},
            )
    return result


@router.get("/webhooks")
def webhook_status(db: DbDep, _principal: AnyPrincipalDep) -> dict[str, WebhookLast | None]:
    """The last notification each app sent, for the Integrations page."""
    with db.read() as session:
        out: dict[str, WebhookLast | None] = {}
        kinds: tuple[Kind, ...] = ("sonarr", "radarr")
        for kind in kinds:
            raw = settings_store.get(session, _status_key(kind))
            out[kind] = WebhookLast.model_validate(raw) if raw else None
        return out
