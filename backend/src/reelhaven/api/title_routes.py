"""Titles (movie/series folders) and their original language."""

from functools import cache

import pycountry
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select

from reelhaven import audit
from reelhaven.api.deps import (
    AnyPrincipalDep,
    DbDep,
    InteractiveDep,
    csrf_protect,
    require_setup_done,
)
from reelhaven.api.schemas import StrictModel
from reelhaven.db import Library, MediaFile, Title
from reelhaven.media.languages import normalise

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])


class TitleOut(BaseModel):
    id: int
    folder: str
    name: str
    year: int | None
    original_language: str | None
    language_source: str
    source_detail: str | None
    file_count: int


class TitlePage(BaseModel):
    total: int
    items: list[TitleOut]


class LanguageOption(BaseModel):
    code: str
    name: str
    alpha2: str | None = None  # e.g. "en", to match the browser's language


class LanguageOverride(StrictModel):
    # A language code or name; null removes the override (resolved again on next scan).
    language: str | None


@cache
def _languages() -> list[LanguageOption]:
    """Every language with a two-letter ISO code: the ones media actually uses."""
    options = [
        LanguageOption(code=lang.alpha_3, name=lang.name, alpha2=lang.alpha_2)
        for lang in pycountry.languages
        if hasattr(lang, "alpha_2")
    ]
    return sorted(options, key=lambda o: o.name)


@router.get("/languages")
def list_languages(_principal: AnyPrincipalDep) -> list[LanguageOption]:
    return _languages()


@router.get("/libraries/{library_id}/titles")
def list_titles(
    library_id: int,
    db: DbDep,
    _principal: AnyPrincipalDep,
    q: str = Query(default="", max_length=200),
    unknown: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> TitlePage:
    counts = (
        select(MediaFile.title_id, func.count().label("n")).group_by(MediaFile.title_id).subquery()
    )
    query = (
        select(Title, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.title_id == Title.id)
        .where(Title.library_id == library_id)
    )
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Title.folder.ilike(f"%{escaped}%", escape="\\"))
    if unknown:
        query = query.where(Title.original_language.is_(None))
    with db.read() as session:
        if session.get(Library, library_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "library_not_found")
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = session.execute(query.order_by(Title.folder).offset(offset).limit(limit)).all()
        items = [
            TitleOut(
                id=title.id,
                folder=title.folder,
                name=title.name,
                year=title.year,
                original_language=title.original_language,
                language_source=title.language_source,
                source_detail=title.source_detail,
                file_count=count,
            )
            for title, count in rows
        ]
    return TitlePage(total=total, items=items)


@router.put("/titles/{title_id}/language")
def set_title_language(
    title_id: int, body: LanguageOverride, db: DbDep, principal: InteractiveDep
) -> dict[str, str | None]:
    language = None
    if body.language is not None:
        language = normalise(body.language)
        if language is None or not pycountry.languages.get(alpha_3=language):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_language")
    with db.write() as session:
        title = session.get(Title, title_id)
        if title is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "title_not_found")
        if language is None:
            # Back to automatic: looked up again on the next scan or refresh.
            title.original_language = None
            title.language_source = "unknown"
            title.source_detail = None
            title.resolved_at = None
        else:
            title.original_language = language
            title.language_source = "manual"
            title.source_detail = f"Set by {principal.actor}"
        audit.record(
            session, principal.actor, "title.language_set", title.folder, {"language": language}
        )
        return {
            "original_language": title.original_language,
            "language_source": title.language_source,
        }


@router.post("/libraries/{library_id}/languages/refresh", status_code=status.HTTP_202_ACCEPTED)
def refresh_languages(
    library_id: int, request: Request, db: DbDep, _principal: InteractiveDep
) -> dict[str, bool]:
    """Look up every title's language again (manual overrides are kept)."""
    with db.read() as session:
        if session.get(Library, library_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "library_not_found")
    return {"started": request.app.state.scanner.start(library_id, languages_only=True)}
