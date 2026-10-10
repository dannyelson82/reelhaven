"""The review page (ADR-0032): files that need a decision, and ignoring them."""

import threading
import time
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from reelhaven import audit
from reelhaven.api.deps import (
    AnyPrincipalDep,
    DbDep,
    InteractiveDep,
    csrf_protect,
    require_setup_done,
)
from reelhaven.api.schemas import StrictModel
from reelhaven.db import Database, MediaFile
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
