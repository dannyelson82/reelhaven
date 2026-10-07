"""Tell Plex, Sonarr and Radarr about replaced files (ARCHITECTURE.md §6.9, ADR-0025).

Every ``BATCH_S`` the notifier picks up jobs that replaced a file since the
last round, groups them by folder, and asks each enabled integration to look
again: Plex scans just those folders, Sonarr/Radarr rescan the affected series
or movies. A whole season finishing is one notification, not twenty.
"""

import logging
import threading
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from pathlib import PurePosixPath
from typing import Any

import httpx
from pydantic import BaseModel
from sqlalchemy import select

from reelhaven import settings_store
from reelhaven.db import Database, Integration, Job, JobResult
from reelhaven.db.types import utcnow
from reelhaven.integrations.clients import ArrClient, IntegrationError, PlexClient
from reelhaven.integrations.pathmap import to_remote
from reelhaven.integrations.service import client_for
from reelhaven.secretbox import SecretBox

logger = logging.getLogger(__name__)

BATCH_S = 60.0
OVERLAP = timedelta(minutes=10)
NOTIFY_KINDS = ("plex", "sonarr", "radarr")


class NotifyStatus(BaseModel):
    at: datetime
    ok: bool
    message: str


def status_key(integration_id: int) -> str:
    return f"notify_last_{integration_id}"


# --- pure matching ---------------------------------------------------------------------------


def _inside(path: str, root: str) -> bool:
    p, r = PurePosixPath(path), PurePosixPath(root)
    return p == r or r in p.parents


def plex_targets(
    folders: Iterable[str], sections: list[tuple[str, list[str]]]
) -> set[tuple[str, str]]:
    """(section key, folder) for every folder inside one of Plex's library locations."""
    targets: set[tuple[str, str]] = set()
    for folder in folders:
        for key, locations in sections:
            if any(_inside(folder, location) for location in locations):
                targets.add((key, folder))
                break
    return targets


def arr_targets(folders: Iterable[str], titles: list[dict[str, Any]]) -> set[int]:
    """Ids of the series/movies whose folder contains one of ``folders``."""
    ids: set[int] = set()
    for folder in folders:
        for title in titles:
            path = title.get("path") or title.get("folderName")
            usable = isinstance(path, str) and path and isinstance(title.get("id"), int)
            if usable and _inside(folder, str(path)):
                ids.add(title["id"])
    return ids


# --- the background thread -------------------------------------------------------------------


class Notifier:
    def __init__(
        self,
        db: Database,
        box: Callable[[], SecretBox],
        transport: Callable[[], httpx.BaseTransport | None] = lambda: None,
    ) -> None:
        self._db = db
        self._box = box
        self._transport = transport
        # Jobs finish out of order (several devices), so no "highest id" cursor: look
        # at jobs finished since the last round (with an overlap) and skip handled ones.
        self._since: datetime | None = None
        self._handled: dict[int, datetime] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.prime()
        self._thread = threading.Thread(target=self._loop, name="notifier", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(5)

    def prime(self) -> None:
        """Start from now: files replaced before a restart aren't re-sent."""
        self._since = utcnow()
        self._handled.clear()

    def _loop(self) -> None:
        while not self._stop.wait(BATCH_S):
            try:
                self.flush()
            except Exception:
                logger.exception("notifying media servers failed")

    def flush(self) -> int:
        """Notify about files replaced since the last round; returns how many folders."""
        if self._since is None:
            self.prime()
        assert self._since is not None  # noqa: S101
        now = utcnow()
        with self._db.read() as session:
            found = session.execute(
                select(JobResult.job_id, Job.source_path)
                .join(Job, Job.id == JobResult.job_id)
                .where(
                    Job.finished_at >= self._since - OVERLAP,
                    JobResult.outcome == "replaced",
                )
            ).all()
            integrations = [
                (i.id, i.kind, i.name, list(i.path_mappings or []), i)
                for i in session.scalars(
                    select(Integration).where(
                        Integration.enabled, Integration.kind.in_(NOTIFY_KINDS)
                    )
                )
            ]
        rows = [(job_id, path) for job_id, path in found if job_id not in self._handled]
        for job_id, _ in rows:
            self._handled[job_id] = now
        self._since = now
        for job_id, at in list(self._handled.items()):
            if now - at > OVERLAP * 6:
                del self._handled[job_id]
        folders = sorted({str(PurePosixPath(path).parent) for _, path in rows})
        if not folders:
            return 0
        for integration_id, kind, name, mappings, row in integrations:
            remote = [to_remote(folder, mappings) for folder in folders]
            try:
                with client_for(row, self._box(), self._transport()) as client:
                    if kind == "plex" and isinstance(client, PlexClient):
                        targets = plex_targets(remote, client.sections())
                        for section, folder in sorted(targets):
                            client.refresh(section, folder)
                        status = NotifyStatus(
                            at=utcnow(), ok=True, message=_done(len(targets), "folder")
                        )
                    elif isinstance(client, ArrClient):
                        ids = arr_targets(remote, client.titles())
                        for item_id in sorted(ids):
                            client.rescan(item_id)
                        what = "series" if kind == "sonarr" else "movie"
                        status = NotifyStatus(at=utcnow(), ok=True, message=_done(len(ids), what))
                    else:
                        continue
            except IntegrationError as exc:
                logger.warning("notify failed", extra={"integration": name, "error": exc.message})
                status = NotifyStatus(at=utcnow(), ok=False, message=exc.message)
            with self._db.write() as session:
                settings_store.put(
                    session, status_key(integration_id), status.model_dump(mode="json")
                )
        return len(folders)


def _done(count: int, what: str) -> str:
    if count == 0:
        return f"Nothing to refresh: no {what} matched (check the path mappings)."
    plural = what if what == "series" or count == 1 else f"{what}s"
    return f"Asked to refresh {count} {plural}."
