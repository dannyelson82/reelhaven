"""The review record (ADR-0033): what the Review page listed, kept after it's resolved.

``reconcile`` is pure: given the open entries and the current review items it says what
to add, refresh and resolve. ``record`` applies that whenever the review list is worked
out afresh, and removes entries resolved more than ``KEEP_DAYS`` ago.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, select

from reelhaven.db import Database, ReviewLogEntry
from reelhaven.db.types import utcnow
from reelhaven.review import ReviewItem

KEEP_DAYS = 90

Key = tuple[int, str]  # (media file id, kind)


@dataclass(frozen=True)
class Changes:
    new: list[ReviewItem]
    seen: dict[int, ReviewItem]  # open entry id -> the item that is still there
    resolved: list[int]  # open entry ids no longer listed


def reconcile(open_entries: dict[Key, int], items: Iterable[ReviewItem]) -> Changes:
    new: list[ReviewItem] = []
    seen: dict[int, ReviewItem] = {}
    for item in items:
        entry = open_entries.get((item.file_id, item.kind))
        if entry is None:
            new.append(item)
        else:
            seen[entry] = item
    resolved = [entry for entry in open_entries.values() if entry not in seen]
    return Changes(new, seen, resolved)


def record(db: Database, items: list[ReviewItem]) -> None:
    now = utcnow()
    with db.write() as session:
        open_rows = session.scalars(
            select(ReviewLogEntry).where(ReviewLogEntry.resolved_at.is_(None))
        ).all()
        by_id = {row.id: row for row in open_rows}
        open_entries = {
            (row.media_file_id, row.kind): row.id
            for row in open_rows
            if row.media_file_id is not None
        }
        changes = reconcile(open_entries, items)
        for entry_id, item in changes.seen.items():
            row = by_id[entry_id]
            row.last_seen_at = now
            row.detail = item.detail
            row.relative_path = item.relative_path
        # A deleted file's entries (file id gone) are resolved too.
        orphans = [row.id for row in open_rows if row.media_file_id is None]
        for entry_id in [*changes.resolved, *orphans]:
            by_id[entry_id].resolved_at = now
        for item in changes.new:
            session.add(
                ReviewLogEntry(
                    media_file_id=item.file_id,
                    library_name=item.library_name,
                    relative_path=item.relative_path,
                    kind=item.kind,
                    detail=item.detail,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        session.execute(
            delete(ReviewLogEntry).where(
                ReviewLogEntry.resolved_at < now - timedelta(days=KEEP_DAYS)
            )
        )


def resolved_since(db: Database, days: int = KEEP_DAYS) -> list[ReviewLogEntry]:
    """Entries resolved in the last ``days``, newest first."""
    with db.read() as session:
        rows = session.scalars(
            select(ReviewLogEntry)
            .where(ReviewLogEntry.resolved_at >= utcnow() - timedelta(days=days))
            .order_by(ReviewLogEntry.resolved_at.desc())
        ).all()
        session.expunge_all()
        return list(rows)
