"""The replacer (ARCHITECTURE.md §6.8, ADR-0016).

Original → recycle bin, verified output → original's place. Both steps are
renames on one filesystem; if the second fails, the first is undone. The
original must still be exactly the file that was planned.
"""

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class ReplaceError(Exception):
    pass


@dataclass(frozen=True)
class Snapshot:
    size: int
    mtime_ns: int


def check_unchanged(path: Path, expected: Snapshot) -> os.stat_result:
    try:
        st = path.stat()
    except FileNotFoundError as exc:
        raise ReplaceError("the original file is gone") from exc
    if (st.st_size, st.st_mtime_ns) != (expected.size, expected.mtime_ns):
        raise ReplaceError("the original file changed since it was planned; scan and try again")
    return st


def _same_device(*paths: Path) -> bool:
    return len({p.stat().st_dev for p in paths}) == 1


def _copy_owner_and_mode(target: Path, like: os.stat_result) -> None:
    target.chmod(like.st_mode & 0o7777)
    try:
        os.chown(target, like.st_uid, like.st_gid)
    except PermissionError:
        # Only possible as root or when already matching; the container runs
        # as PUID/PGID, which normally owns the media already.
        if (target.stat().st_uid, target.stat().st_gid) != (like.st_uid, like.st_gid):
            logger.warning(
                "could not keep the original file owner",
                extra={"path": str(target), "uid": like.st_uid, "gid": like.st_gid},
            )


def replace_with(original: Path, output: Path, recycle_target: Path, expected: Snapshot) -> None:
    """Move ``original`` to ``recycle_target`` and ``output`` into its place."""
    st = check_unchanged(original, expected)
    recycle_target.parent.mkdir(parents=True, exist_ok=True)
    if not _same_device(original, output, recycle_target.parent):
        raise ReplaceError(
            "the library, its .reelhaven folder and the new file aren't on the same disk; "
            "refusing to copy (ADR-0016)"
        )
    if recycle_target.exists():
        raise ReplaceError("a recycle bin entry with that name already exists")
    _copy_owner_and_mode(output, st)

    original.rename(recycle_target)
    try:
        output.rename(original)
    except OSError as exc:
        recycle_target.rename(original)  # put the original back
        raise ReplaceError(f"could not move the new file into place: {exc}") from exc


def restore(stored: Path, original: Path, current_to: Path) -> None:
    """Put a recycled file back. Whatever is at ``original`` now goes to ``current_to``."""
    if not stored.exists():
        raise ReplaceError("the recycled file is no longer there")
    original.parent.mkdir(parents=True, exist_ok=True)
    moved_current = False
    if original.exists():
        current_to.parent.mkdir(parents=True, exist_ok=True)
        if not _same_device(stored, original, current_to.parent):
            raise ReplaceError("files are on different disks; refusing to copy")
        original.rename(current_to)
        moved_current = True
    try:
        stored.rename(original)
    except OSError as exc:
        if moved_current:
            current_to.rename(original)
        raise ReplaceError(f"could not restore: {exc}") from exc


def remove_tree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
