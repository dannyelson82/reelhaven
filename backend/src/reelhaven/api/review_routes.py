"""The review page (ADR-0032): files that need a decision, and ignoring them."""

import threading
import time
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from reelhaven import audit
from reelhaven.api.deps import (
    AnyPrincipalDep,
    DbDep,
    InteractiveDep,
    csrf_protect,
    require_setup_done,
)
from reelhaven.api.schemas import StrictModel
from reelhaven.db import Database, Job, Library, MediaFile
from reelhaven.dryrun import plan_library
from reelhaven.jobs import wrong_language
from reelhaven.jobs.service import ACTIVE
from reelhaven.jobs.wrong_language import WrongLanguageAction
from reelhaven.review import KINDS, ReviewItem, ReviewKind, file_state, gather, review_items

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])

# Planning every library takes a moment on big ones; the page polls, so keep the result
# briefly. Ignoring a file clears it.
CACHE_SECONDS = 15.0
_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()


def _all_items(db: Database) -> list[ReviewItem]:
    with _cache_lock:
        if _cache.get("db") is db and time.monotonic() - _cache["at"] < CACHE_SECONDS:
            items: list[ReviewItem] = _cache["items"]
            return items
    items = review_items(gather(db))
    with _cache_lock:
        _cache.update(db=db, at=time.monotonic(), items=items)
    return items


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


class ReviewItemOut(BaseModel):
    kind: ReviewKind
    file_id: int
    library_id: int
    library_name: str
    relative_path: str
    size: int
    detail: str
    ignored: bool
    job_id: int | None
    original_language: str | None
    audio_languages: list[str]


class ReviewPage(BaseModel):
    counts: dict[str, int]  # per kind, ignored items left out
    ignored: int
    total: int  # matching this page's filters
    items: list[ReviewItemOut]


@router.get("/review")
def get_review(
    db: DbDep,
    _principal: AnyPrincipalDep,
    kind: ReviewKind | None = None,
    library_id: int | None = None,
    show_ignored: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> ReviewPage:
    items = [i for i in _all_items(db) if library_id is None or i.library_id == library_id]
    counts: dict[str, int] = {
        k: sum(1 for i in items if i.kind == k and not i.ignored) for k in KINDS
    }
    chosen = [
        i for i in items if (kind is None or i.kind == kind) and (show_ignored or not i.ignored)
    ]
    chosen.sort(key=lambda i: (KINDS.index(i.kind), i.library_name, i.relative_path))
    return ReviewPage(
        counts=counts,
        ignored=sum(1 for i in items if i.ignored),
        total=len(chosen),
        items=[ReviewItemOut(**asdict(i)) for i in chosen[offset : offset + limit]],
    )


class IgnoreIn(StrictModel):
    file_id: int
    kind: ReviewKind
    ignored: bool = True


@router.put("/review/ignore", status_code=status.HTTP_204_NO_CONTENT)
def ignore(body: IgnoreIn, request: Request, db: DbDep, principal: InteractiveDep) -> None:
    """Ignore one kind of problem on a file until the file changes (or show it again)."""
    with db.write() as session:
        media_file = session.get(MediaFile, body.file_id)
        if media_file is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "file_not_found")
        ignored = dict(media_file.review_ignored or {})
        if body.ignored:
            ignored[body.kind] = file_state(media_file.size, media_file.mtime_ns)
        else:
            ignored.pop(body.kind, None)
        media_file.review_ignored = ignored or None
        audit.record(
            session,
            principal.actor,
            "review.ignored" if body.ignored else "review.unignored",
            media_file.relative_path,
            {"kind": body.kind},
        )
    clear_cache()


class WrongLanguageIn(StrictModel):
    action: WrongLanguageAction


@router.post("/files/{file_id}/wrong-language", status_code=status.HTTP_201_CREATED)
def act_on_wrong_language(
    file_id: int, body: WrongLanguageIn, request: Request, db: DbDep, principal: InteractiveDep
) -> dict[str, int]:
    """Quarantine or delete one wrong-language file and ask for another release."""
    with db.read() as session:
        media_file = session.get(MediaFile, file_id)
        if media_file is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "file_not_found")
        library_id = media_file.library_id
    plan = next((p for p in plan_library(db, library_id) if p.file_id == file_id), None)
    flags = plan.plan.flags if plan and plan.plan else []
    if "wrong_language" not in flags and "no_wanted_audio" not in flags:
        raise HTTPException(status.HTTP_409_CONFLICT, "not_wrong_language")
    with db.write() as session:
        media_file = session.get(MediaFile, file_id)
        library = session.get(Library, library_id)
        if media_file is None or library is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "file_not_found")
        busy = session.scalars(
            select(Job.id).where(Job.media_file_id == file_id, Job.status.in_(ACTIVE))
        ).first()
        if busy is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "file_busy")
        job = wrong_language.create_job(session, library, media_file, body.action, principal.actor)
        job_id = job.id
    request.app.state.queue.notify()
    clear_cache()
    return {"job_id": job_id}
