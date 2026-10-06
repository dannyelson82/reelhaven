"""Scanning and browsing the files of a library. Read-only on disk."""

from dataclasses import asdict
from datetime import datetime
from typing import Any

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
from reelhaven.db import Library, MediaFile
from reelhaven.media.info import MediaInfo, Stream
from reelhaven.scanner import Scanner

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])


class ScanStatus(BaseModel):
    state: str
    phase: str
    found: int
    to_probe: int
    probed: int
    failed: int
    unchanged: int
    moved: int
    removed: int
    unstable: int
    error: str | None
    started_at: float
    finished_at: float | None


class FileSummary(BaseModel):
    id: int
    relative_path: str
    size: int
    status: str
    duration_s: float | None = None
    video_codec: str | None = None
    width: int | None = None
    height: int | None = None
    hdr: str | None = None
    audio_languages: list[str | None] = []
    subtitle_languages: list[str | None] = []
    probe_error: str | None = None


class FileDetail(FileSummary):
    path: str
    container: str | None = None
    bit_rate: int | None = None
    streams: list[Stream] = []
    probed_at: datetime | None = None


class FilePage(BaseModel):
    total: int
    items: list[FileSummary]


def _scanner(request: Request) -> Scanner:
    scanner: Scanner = request.app.state.scanner
    return scanner


def _library(db: Any, library_id: int) -> Library:
    with db.read() as session:
        library: Library | None = session.get(Library, library_id)
    if library is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "library_not_found")
    return library


def _summary_fields(row: MediaFile) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "id": row.id,
        "relative_path": row.relative_path,
        "size": row.size,
        "status": row.status,
        "probe_error": row.probe_error,
    }
    if row.probe is not None:
        info = MediaInfo.model_validate(row.probe)
        video = info.video
        fields.update(
            duration_s=info.duration_s,
            video_codec=video.codec if video else None,
            width=video.width if video else None,
            height=video.height if video else None,
            hdr=video.hdr if video else None,
            audio_languages=[s.language for s in info.of_kind("audio")],
            subtitle_languages=[s.language for s in info.of_kind("subtitle")],
        )
    return fields


@router.post("/libraries/{library_id}/scan", status_code=status.HTTP_202_ACCEPTED)
def start_scan(
    library_id: int, request: Request, db: DbDep, principal: InteractiveDep
) -> dict[str, bool]:
    library = _library(db, library_id)
    started = _scanner(request).start(library_id)
    if started:
        with db.write() as session:
            audit.record(session, principal.actor, "library.scan_started", library.name)
    return {"started": started}


@router.get("/libraries/{library_id}/scan")
def scan_status(
    library_id: int, request: Request, db: DbDep, _principal: AnyPrincipalDep
) -> ScanStatus | None:
    _library(db, library_id)
    progress = _scanner(request).progress(library_id)
    return None if progress is None else ScanStatus(**asdict(progress))


@router.get("/libraries/{library_id}/files")
def list_files(
    library_id: int,
    db: DbDep,
    _principal: AnyPrincipalDep,
    q: str = Query(default="", max_length=200),
    problems: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> FilePage:
    _library(db, library_id)
    query = select(MediaFile).where(MediaFile.library_id == library_id)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(MediaFile.relative_path.ilike(f"%{escaped}%", escape="\\"))
    if problems:
        query = query.where(MediaFile.status != "ok")
    with db.read() as session:
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = session.scalars(
            query.order_by(MediaFile.relative_path).offset(offset).limit(limit)
        ).all()
        items = [FileSummary(**_summary_fields(row)) for row in rows]
    return FilePage(total=total, items=items)


@router.get("/files/{file_id}")
def get_file(file_id: int, db: DbDep, _principal: AnyPrincipalDep) -> FileDetail:
    with db.read() as session:
        row = session.get(MediaFile, file_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "file_not_found")
        fields = _summary_fields(row)
        detail = FileDetail(**fields, path=row.path, probed_at=row.probed_at)
        if row.probe is not None:
            info = MediaInfo.model_validate(row.probe)
            detail.container = info.container
            detail.bit_rate = info.bit_rate
            detail.streams = info.streams
    return detail
