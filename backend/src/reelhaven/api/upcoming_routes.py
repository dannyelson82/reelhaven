"""Upcoming work: files that still need a job and aren't queued yet (Jobs → Upcoming).

Automatic libraries keep only a few jobs queued (enough to fill every worker, ADR-0025);
this shows the rest of the backlog, in the order it will run.
"""

import threading
import time
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from reelhaven.api.deps import AnyPrincipalDep, DbDep, csrf_protect, require_setup_done
from reelhaven.automation import FileState, Upcoming, UpcomingWhy, given_up, upcoming
from reelhaven.db import Database, Job, Library, MediaFile
from reelhaven.dryrun import plan_library
from reelhaven.encode_planner import profile_fingerprint
from reelhaven.jobs.service import ACTIVE, library_profile
from reelhaven.policy import LanguagePolicy

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])

CACHE_SECONDS = 15.0  # planning every library takes a moment on big ones
_cache: dict[str, Any] = {}
_lock = threading.Lock()


class UpcomingOut(BaseModel):
    file_id: int
    relative_path: str
    action: str
    saved: int | None
    why: UpcomingWhy
    library_id: int
    library_name: str


class UpcomingPage(BaseModel):
    total: int  # matching the filter
    counts: dict[str, int]  # per reason, all libraries
    saved: int  # estimated total of the matching files whose saving is known
    items: list[UpcomingOut]


def _gather(db: Database) -> list[tuple[int, str, Upcoming]]:
    with _lock:
        if _cache.get("db") is db and time.monotonic() - _cache["at"] < CACHE_SECONDS:
            cached: list[tuple[int, str, Upcoming]] = _cache["items"]
            return cached
    with db.read() as session:
        libraries = list(session.scalars(select(Library).order_by(Library.id)))
        facts = []
        for library in libraries:
            profile = library_profile(session, library)
            active = {
                f
                for f in session.scalars(
                    select(Job.media_file_id).where(
                        Job.library_id == library.id, Job.status.in_(ACTIVE)
                    )
                )
                if f is not None
            }
            current = {
                f.id: FileState(f.size, f.mtime_ns)
                for f in session.scalars(
                    select(MediaFile).where(MediaFile.library_id == library.id)
                )
            }
            facts.append(
                (
                    library.id,
                    library.name,
                    library.watch_mode == "automatic",
                    profile is not None
                    and library.test_run_profile == profile_fingerprint(profile),
                    LanguagePolicy.model_validate(
                        library.language_policy or {}
                    ).wrong_language_action,
                    active,
                    given_up(session, library.id),
                    current,
                )
            )
    items: list[tuple[int, str, Upcoming]] = []
    for library_id, name, automatic, allowed, action, active, gave_up, current in facts:
        for entry in upcoming(
            plan_library(db, library_id),
            automatic=automatic,
            active=active,
            gave_up=gave_up,
            current=current,
            encodes_allowed=allowed,
            wrong_language_action=action,
        ):
            items.append((library_id, name, entry))
    with _lock:
        _cache.update(db=db, at=time.monotonic(), items=items)
    return items


@router.get("/upcoming")
def get_upcoming(
    db: DbDep,
    _principal: AnyPrincipalDep,
    why: UpcomingWhy | None = None,
    library_id: int | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> UpcomingPage:
    everything = _gather(db)
    counts = {
        w: sum(1 for _l, _n, u in everything if u.why == w)
        for w in ("next", "test_run", "not_automatic")
    }
    chosen = [
        (lid, name, u)
        for lid, name, u in everything
        if (why is None or u.why == why) and (library_id is None or lid == library_id)
    ]
    return UpcomingPage(
        total=len(chosen),
        counts=counts,
        saved=sum(u.saved or 0 for _l, _n, u in chosen),
        items=[
            UpcomingOut(**asdict(u), library_id=lid, library_name=name)
            for lid, name, u in chosen[offset : offset + limit]
        ],
    )
