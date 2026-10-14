"""Stop all processing while a disk is full, and carry on once there is room again.

When a job runs out of disk space, nothing is gained by starting the next one: it
would fail the same way. The job goes back in the queue (its original was never
touched), a hold is stored, and no job starts until every disk the job needed has
room for it again. The queue checks that by itself every ``CHECK_EVERY_S`` seconds.
"""

import errno
import shutil
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from reelhaven import settings_store
from reelhaven.db import Database
from reelhaven.db.models import Setting

KEY = "space_hold"
CHECK_EVERY_S = 30.0
# Room asked for on top of the file itself: logs, the database and other writers.
MARGIN_BYTES = 2 * 1024**3

_MESSAGES = ("no space left on device", "disk quota exceeded")


class SpaceHold(BaseModel):
    model_config = ConfigDict(extra="forbid")

    since: datetime
    paths: list[str]  # folders whose disks need room before work carries on
    needed_bytes: int  # free space each of them needs
    error: str  # what the job reported, for the banner


def is_out_of_space(exc: BaseException) -> bool:
    """Whether a job failure (or anything it was raised from) means a disk is full."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, OSError) and current.errno in (errno.ENOSPC, errno.EDQUOT):
            return True
        if any(message in str(current).lower() for message in _MESSAGES):
            return True
        current = current.__cause__ or current.__context__
    return False


def needed_for(source_size: int | None) -> int:
    """Free space a job needs: room for a full-size copy of its file, plus a margin."""
    return (source_size or 0) + MARGIN_BYTES


def has_room(free: Mapping[str, int], needed: int) -> bool:
    """Whether every disk has at least ``needed`` bytes free."""
    return all(value >= needed for value in free.values())


def free_space(paths: Iterable[str]) -> dict[str, int]:
    """Free bytes on the disk holding each path. A folder that doesn't exist yet is
    measured at its nearest existing parent; one that can't be measured counts as full."""
    out: dict[str, int] = {}
    for raw in paths:
        path = Path(raw)
        while not path.exists() and path != path.parent:
            path = path.parent
        try:
            out[raw] = shutil.disk_usage(path).free
        except OSError:
            out[raw] = 0
    return out


def load(session: Session) -> SpaceHold | None:
    raw = settings_store.get(session, KEY)
    return None if raw is None else SpaceHold.model_validate(raw)


def save(session: Session, hold: SpaceHold) -> None:
    settings_store.put(session, KEY, hold.model_dump(mode="json"))


def clear(session: Session) -> bool:
    """Remove the hold; returns whether there was one."""
    row = session.get(Setting, KEY)
    if row is None:
        return False
    session.delete(row)
    return True


def merged(current: SpaceHold | None, new: SpaceHold) -> SpaceHold:
    """Several jobs can run out of space at once: wait for room for all of them."""
    if current is None:
        return new
    return SpaceHold(
        since=current.since,
        paths=sorted({*current.paths, *new.paths}),
        needed_bytes=max(current.needed_bytes, new.needed_bytes),
        error=current.error,
    )


def is_held(db: Database) -> bool:
    with db.read() as session:
        return session.get(Setting, KEY) is not None
