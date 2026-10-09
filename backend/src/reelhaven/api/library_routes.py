"""Libraries and the folder browser. Files on disk are never touched here."""

import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from reelhaven import audit
from reelhaven.api.deps import (
    AnyPrincipalDep,
    DbDep,
    InteractiveDep,
    csrf_protect,
    require_setup_done,
)
from reelhaven.api.schemas import StrictModel
from reelhaven.config import Settings
from reelhaven.db import Library, MediaFile
from reelhaven.encode_planner import profile_fingerprint
from reelhaven.jobs.service import library_profile
from reelhaven.paths import INTERNAL_DIR, PathNotAllowedError, overlaps, resolve_within
from reelhaven.policy import LanguagePolicy

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])

LibraryType = Literal["movies", "tv", "other"]
WatchMode = Literal["off", "watch", "automatic"]
MAX_BROWSE_ENTRIES = 2000


def media_root(request: Request) -> Path:
    settings: Settings = request.app.state.settings
    root = settings.media_root
    if not root.is_dir():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "media_root_missing")
    return root.resolve()


MediaRootDep = Annotated[Path, Depends(media_root)]


class LibraryOut(BaseModel):
    id: int
    name: str
    type: LibraryType
    path: str
    relative_path: str
    created_at: datetime
    file_count: int = 0
    last_scan_at: datetime | None = None
    last_scan_error: str | None = None
    scanning: bool = False
    watch_mode: WatchMode = "off"
    # The library has a profile but no test run approved with it, so whole-library
    # re-encoding (manual or Automatic) waits (ADR-0020).
    needs_test_run: bool = False


class LibraryCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    type: LibraryType
    path: str = Field(max_length=4096)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name can't be blank")
        return value


class LibraryUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: LibraryType | None = None
    watch_mode: WatchMode | None = None

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return None if value is None else value.strip() or None


class BrowseEntry(BaseModel):
    name: str
    path: str  # relative to the media root


class BrowseResult(BaseModel):
    path: str
    parent: str | None
    dirs: list[BrowseEntry]
    truncated: bool


def _needs_test_run(session: Session, library: Library) -> bool:
    profile = library_profile(session, library)
    return profile is not None and library.test_run_profile != profile_fingerprint(profile)


def _out(
    library: Library,
    root: Path,
    file_count: int = 0,
    scanning: bool = False,
    needs_test_run: bool = False,
) -> LibraryOut:
    path = Path(library.path)
    relative = path.relative_to(root) if path.is_relative_to(root) else path
    return LibraryOut(
        id=library.id,
        name=library.name,
        type=library.type,  # type: ignore[arg-type]
        path=library.path,
        relative_path=str(relative),
        created_at=library.created_at,
        file_count=file_count,
        last_scan_at=library.last_scan_at,
        last_scan_error=library.last_scan_error,
        scanning=scanning,
        watch_mode=library.watch_mode,  # type: ignore[arg-type]
        needs_test_run=needs_test_run,
    )


def _file_counts(session: Any) -> dict[int, int]:
    rows = session.execute(
        select(MediaFile.library_id, func.count()).group_by(MediaFile.library_id)
    ).all()
    return {library_id: count for library_id, count in rows}


def _relative(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    return "" if rel == Path() else rel.as_posix()


@router.get("/browse")
def browse(root: MediaRootDep, _principal: InteractiveDep, path: str = "") -> BrowseResult:
    """List sub-folders of a folder inside the media root (folder picker)."""
    try:
        folder = resolve_within(root, path)
    except PathNotAllowedError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "path_not_allowed") from exc
    if not folder.is_dir():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "not_a_folder")

    dirs: list[BrowseEntry] = []
    truncated = False
    try:
        entries = sorted(os.scandir(folder), key=lambda e: e.name.casefold())
    except OSError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "folder_unreadable") from exc
    for entry in entries:
        if entry.name.startswith(".") or entry.name == INTERNAL_DIR:
            continue
        try:
            if not entry.is_dir():
                continue
            child = resolve_within(root, Path(entry.path))
        except (PathNotAllowedError, OSError):
            continue  # e.g. a symlink pointing outside /media
        if len(dirs) >= MAX_BROWSE_ENTRIES:
            truncated = True
            break
        dirs.append(BrowseEntry(name=entry.name, path=_relative(child, root)))

    parent = None if folder == root else _relative(folder.parent, root)
    return BrowseResult(path=_relative(folder, root), parent=parent, dirs=dirs, truncated=truncated)


@router.get("/libraries")
def list_libraries(
    request: Request, db: DbDep, root: MediaRootDep, _principal: AnyPrincipalDep
) -> list[LibraryOut]:
    scanner = request.app.state.scanner
    with db.read() as session:
        libraries = session.scalars(select(Library).order_by(Library.name)).all()
        counts = _file_counts(session)
        waiting = {lib.id: _needs_test_run(session, lib) for lib in libraries}
    return [
        _out(lib, root, counts.get(lib.id, 0), scanner.is_running(lib.id), waiting[lib.id])
        for lib in libraries
    ]


@router.post("/libraries", status_code=status.HTTP_201_CREATED)
def create_library(
    body: LibraryCreate, db: DbDep, root: MediaRootDep, principal: InteractiveDep
) -> LibraryOut:
    try:
        folder = resolve_within(root, body.path)
    except PathNotAllowedError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "path_not_allowed") from exc
    if not folder.is_dir():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "not_a_folder")
    if folder == root:
        # A library at the root would contain every future library.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "choose_a_subfolder")

    with db.write() as session:
        for other in session.scalars(select(Library)):
            if overlaps(folder, Path(other.path)):
                raise HTTPException(status.HTTP_409_CONFLICT, "path_overlaps_library")
        library = Library(name=body.name, type=body.type, path=str(folder))
        session.add(library)
        try:
            session.flush()
        except IntegrityError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "name_taken") from exc
        audit.record(session, principal.actor, "library.created", body.name, {"path": str(folder)})
        return _out(library, root)


def _get(session_library: Library | None) -> Library:
    if session_library is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "library_not_found")
    return session_library


@router.get("/libraries/{library_id}")
def get_library(
    library_id: int, request: Request, db: DbDep, root: MediaRootDep, _principal: AnyPrincipalDep
) -> LibraryOut:
    with db.read() as session:
        library = _get(session.get(Library, library_id))
        count = _file_counts(session).get(library_id, 0)
        waiting = _needs_test_run(session, library)
    scanning = request.app.state.scanner.is_running(library_id)
    return _out(library, root, count, scanning, waiting)


@router.patch("/libraries/{library_id}")
def update_library(
    library_id: int,
    body: LibraryUpdate,
    request: Request,
    db: DbDep,
    root: MediaRootDep,
    principal: InteractiveDep,
) -> LibraryOut:
    with db.write() as session:
        library = _get(session.get(Library, library_id))
        changes = body.model_dump(exclude_none=True)
        for key, value in changes.items():
            setattr(library, key, value)
        try:
            session.flush()
        except IntegrityError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "name_taken") from exc
        if changes:
            audit.record(session, principal.actor, "library.updated", library.name, changes)
        out = _out(library, root)
    if changes.get("watch_mode") == "automatic":
        request.app.state.automation.poke()  # start right away, not in 30 s
    return out


@router.delete("/libraries/{library_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_library(library_id: int, db: DbDep, principal: InteractiveDep) -> None:
    """Forget a library. Its files, recycle bin and work folders stay on disk."""
    with db.write() as session:
        library = _get(session.get(Library, library_id))
        session.delete(library)
        audit.record(
            session, principal.actor, "library.deleted", library.name, {"path": library.path}
        )


@router.get("/libraries/{library_id}/policy")
def get_policy(library_id: int, db: DbDep, _principal: AnyPrincipalDep) -> LanguagePolicy:
    with db.read() as session:
        library = _get(session.get(Library, library_id))
        return LanguagePolicy.model_validate(library.language_policy or {})


@router.put("/libraries/{library_id}/policy")
def put_policy(
    library_id: int, body: LanguagePolicy, db: DbDep, principal: InteractiveDep
) -> LanguagePolicy:
    with db.write() as session:
        library = _get(session.get(Library, library_id))
        library.language_policy = body.model_dump()
        audit.record(
            session, principal.actor, "library.policy_updated", library.name, body.model_dump()
        )
    return body
