"""Wrong-language files (ADR-0032): quarantine or delete, then ask for another release.

Either way the file leaves the library for its own ``.reelhaven`` folder (a rename on the
same disk, ADR-0016) and is kept for the recycle bin's days to keep: *quarantine* items
show on the Quarantine tab, *delete* items in the recycle bin. Sonarr/Radarr are then
asked to blocklist the release and search for another.
"""

import logging
import os
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from reelhaven import audit
from reelhaven.config import Settings
from reelhaven.db import Database, Job, Library, MediaFile, RecycleItem
from reelhaven.db.types import utcnow
from reelhaven.jobs.pipeline import JobFailedError, discard_now
from reelhaven.jobs.replace import ReplaceError, Snapshot, check_unchanged
from reelhaven.jobs.storage import internal_dir, recycle_path
from reelhaven.planner import Plan
from reelhaven.recycle_settings import keep_days

logger = logging.getLogger(__name__)

WrongLanguageAction = Literal["quarantine", "delete"]
# The recycle item's reason: what the owner sees and which tab it shows on.
REASONS: dict[WrongLanguageAction, str] = {"quarantine": "quarantine", "delete": "wrong-language"}
JOB_TYPE = "wrong_language"


def create_job(
    session: Session,
    library: Library,
    media_file: MediaFile,
    action: WrongLanguageAction,
    actor: str,
) -> Job:
    what = "Quarantine" if action == "quarantine" else "Delete"
    plan = Plan(
        action="skip",
        tracks=[],
        flags=["wrong_language"],
        summary=f"{what}: wrong language",
        details=[
            f"{what} this file (none of its audio is in the library's languages) and ask "
            "Sonarr/Radarr for another release."
        ],
        removed_bytes=0,
    )
    job = Job(
        library_id=library.id,
        media_file_id=media_file.id,
        type=JOB_TYPE,
        source_path=media_file.path,
        source_size=media_file.size,
        source_mtime_ns=media_file.mtime_ns,
        plan={**plan.model_dump(mode="json"), "wrong_language_action": action},
        probe=media_file.probe or {},
        requested_by=actor,
    )
    session.add(job)
    session.flush()
    return job


def _inside(path: Path, root: Path) -> Path:
    """Real path of ``path``, which must lie under ``root`` (paths come from the database)."""
    real_root = os.path.realpath(root)
    real = os.path.realpath(path)
    if not real.startswith(real_root + os.sep):
        raise ReplaceError(f"refusing to touch a path outside the library: {path}")
    return Path(real)


def process(
    db: Database, settings: Settings, job_id: int, research: Callable[[str], list[str]]
) -> None:
    del settings  # same signature as the other job kinds
    with db.read() as session:
        job = session.get(Job, job_id)
        library = session.get(Library, job.library_id) if job and job.library_id else None
        if job is None or library is None:
            return
        action: WrongLanguageAction = job.plan.get("wrong_language_action", "quarantine")
        root = Path(library.path)
        snapshot = Snapshot(job.source_size, job.source_mtime_ns)
        source_path, media_file_id, actor = job.source_path, job.media_file_id, job.requested_by
        library_id, library_name = library.id, library.name
    try:
        source = _inside(Path(source_path), root)
        relative = source.relative_to(os.path.realpath(root)).as_posix()
        stored = recycle_path(root, f"job-{job_id}", relative)
        check_unchanged(source, snapshot)
        stored.parent.mkdir(parents=True, exist_ok=True)
        _inside(stored.parent, internal_dir(root))
        if source.stat().st_dev != stored.parent.stat().st_dev:
            raise ReplaceError("the library and its .reelhaven folder aren't on the same disk")
        if stored.exists():
            raise ReplaceError("a recycle bin entry with that name already exists")
        source.rename(stored)
    except (ReplaceError, OSError, ValueError) as exc:
        raise JobFailedError(str(exc)) from exc

    now = utcnow()
    keep = keep_days(db)
    with db.write() as session:
        item = RecycleItem(
            library_id=library_id,
            job_id=job_id,
            original_path=str(source),
            stored_path=str(stored),
            size=snapshot.size,
            reason=REASONS[action],
            created_at=now,
            expires_at=now + timedelta(days=keep),
        )
        session.add(item)
        session.flush()
        item_id = item.id
        # The file has left the library; the next scan would find it gone anyway.
        if media_file_id is not None and (gone := session.get(MediaFile, media_file_id)):
            session.delete(gone)
        audit.record(
            session,
            actor,
            "file.quarantined" if action == "quarantine" else "file.deleted",
            str(source),
            {"job": job_id, "library": library_name, "size": snapshot.size},
        )
    logger.info("wrong-language file moved aside", extra={"job": job_id, "action": action})

    # Sonarr/Radarr only after the file is safely aside; a failure there doesn't undo it.
    lines = research(str(source))
    with db.write() as session:
        finished = session.get(Job, job_id)
        if finished is not None:
            details = [*finished.plan.get("details", []), *lines]
            finished.plan = {**finished.plan, "details": details}
            finished.status = "done"
            finished.progress = 1.0
            finished.finished_at = utcnow()
    if keep == 0:
        discard_now(db, item_id)
