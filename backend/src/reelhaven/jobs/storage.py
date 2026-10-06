"""Where ReelHaven keeps its own files inside a library (ADR-0016)."""

from pathlib import Path

from reelhaven.paths import INTERNAL_DIR


def internal_dir(library_root: Path) -> Path:
    return library_root / INTERNAL_DIR


def work_dir(library_root: Path, job_id: int) -> Path:
    return internal_dir(library_root) / "work" / str(job_id)


def recycle_path(library_root: Path, item_key: str, relative: str) -> Path:
    return internal_dir(library_root) / "recycle" / item_key / relative
