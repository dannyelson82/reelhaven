"""Creating jobs and managing the recycle bin."""

import logging
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from reelhaven import audit
from reelhaven.db import Database, Job, Library, MediaFile, Profile, RecycleItem
from reelhaven.db.types import utcnow
from reelhaven.dryrun import FilePlan
from reelhaven.jobs.commands import UnsupportedContainerError, remux_format
from reelhaven.jobs.pipeline import discard_now
from reelhaven.jobs.replace import ReplaceError, restore
from reelhaven.jobs.storage import delete_stored, recycle_path
from reelhaven.profiles import ProfileSettings
from reelhaven.recycle_settings import keep_days

logger = logging.getLogger(__name__)

ACTIVE = ("queued", "running", "verifying")


class NotApplicableError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _active_file_ids(session: Session, file_ids: list[int]) -> set[int]:
    rows = session.scalars(
        select(Job.media_file_id).where(Job.media_file_id.in_(file_ids), Job.status.in_(ACTIVE))
    )
    return {r for r in rows if r is not None}


def library_profile(session: Session, library: Library) -> ProfileSettings | None:
    row = session.get(Profile, library.profile_id) if library.profile_id else None
    return ProfileSettings.model_validate(row.settings) if row else None


def create_jobs(session: Session, library: Library, plans: list[FilePlan], actor: str) -> list[Job]:
    """Queue jobs for planned files; skips files without changes or already queued."""
    wanted = [p for p in plans if p.plan is not None and p.plan.action in ("remux", "encode")]
    profile = library_profile(session, library)
    busy = _active_file_ids(session, [p.file_id for p in wanted])
    jobs: list[Job] = []
    for item in wanted:
        if item.file_id in busy:
            continue
        media_file = session.get(MediaFile, item.file_id)
        if media_file is None or media_file.probe is None or item.plan is None:
            continue
        try:
            remux_format(Path(media_file.path))
        except UnsupportedContainerError:
            continue
        encode = item.plan.action == "encode"
        if encode and profile is None:
            continue
        job = Job(
            library_id=library.id,
            media_file_id=media_file.id,
            type="encode" if encode else "remux",
            profile=profile.model_dump() if encode and profile else None,
            source_path=media_file.path,
            source_size=media_file.size,
            source_mtime_ns=media_file.mtime_ns,
            plan=item.plan.model_dump(mode="json"),
            probe=media_file.probe,
            requested_by=actor,
        )
        session.add(job)
        jobs.append(job)
    session.flush()
    return jobs


def check_applicable(item: FilePlan, media_file: MediaFile) -> None:
    if item.plan is None:
        raise NotApplicableError("file_not_readable")
    if item.plan.action not in ("remux", "encode"):
        raise NotApplicableError("nothing_to_do")
    if item.language_pending:
        raise NotApplicableError("language_pending")
    try:
        remux_format(Path(media_file.path))
    except UnsupportedContainerError as exc:
        raise NotApplicableError("unsupported_container") from exc


# --- recycle bin -------------------------------------------------------------------------


def restore_item(db: Database, item_id: int, actor: str) -> RecycleItem:
    """Put an original back. The file currently in its place is recycled, not deleted."""
    with db.read() as session:
        item = session.get(RecycleItem, item_id)
        if item is None:
            raise LookupError("recycle_item_not_found")
        if item.restored_at is not None or item.purged_at is not None:
            raise ReplaceError("this item was already restored or purged")
        library = session.get(Library, item.library_id)
        if library is None:
            raise LookupError("library_not_found")
        root = Path(library.path)
    original = Path(item.original_path)
    stored = Path(item.stored_path)
    key = f"restore-{item_id}-{int(utcnow().timestamp())}"
    relative = original.relative_to(root).as_posix()
    current_to = recycle_path(root, key, relative)
    had_current = original.exists()
    size_current = original.stat().st_size if had_current else 0

    keep = keep_days(db)
    restore(stored, original, current_to, root)

    now = utcnow()
    swap_id: int | None = None
    with db.write() as session:
        row = session.get(RecycleItem, item_id)
        assert row is not None  # noqa: S101
        row.restored_at = now
        if had_current:
            swap = RecycleItem(
                library_id=row.library_id,
                original_path=str(original),
                stored_path=str(current_to),
                size=size_current,
                reason="restore-swap",
                created_at=now,
                expires_at=now + timedelta(days=keep),
            )
            session.add(swap)
            session.flush()
            swap_id = swap.id
        # The library file changed: forget its probe so the next scan reads it again.
        media_file = session.scalars(
            select(MediaFile).where(MediaFile.path == str(original))
        ).first()
        if media_file is not None:
            media_file.mtime_ns = -1
        audit.record(session, actor, "recycle.restored", str(original), {"item": item_id})
    if swap_id is not None and keep == 0:
        discard_now(db, swap_id)
    return row


def purge_item(db: Database, item_id: int, actor: str) -> None:
    with db.read() as session:
        item = session.get(RecycleItem, item_id)
        if item is None:
            raise LookupError("recycle_item_not_found")
        stored = Path(item.stored_path)
    delete_stored(stored)
    with db.write() as session:
        row = session.get(RecycleItem, item_id)
        if row is not None and row.purged_at is None:
            row.purged_at = utcnow()
            audit.record(session, actor, "recycle.purged", row.original_path, {"item": item_id})


def purge_expired(db: Database) -> int:
    """Delete recycle bin entries past their expiry date. Returns how many."""
    now = utcnow()
    with db.read() as session:
        expired = [
            (r.id, Path(r.stored_path))
            for r in session.scalars(
                select(RecycleItem).where(
                    RecycleItem.expires_at < now,
                    RecycleItem.purged_at.is_(None),
                    RecycleItem.restored_at.is_(None),
                )
            )
        ]
    for item_id, stored in expired:
        delete_stored(stored)
        with db.write() as session:
            row = session.get(RecycleItem, item_id)
            if row is not None:
                row.purged_at = now
                audit.record(session, "system", "recycle.expired", row.original_path)
    return len(expired)
