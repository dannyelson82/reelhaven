"""File-system confinement (SECURITY.md "File system confinement").

Every path that comes from the UI, the API or a webhook goes through
``resolve_within`` before it is used. Symlinks are resolved *before* the
containment check, so a link can't point ReelHaven at other host folders.
"""

from pathlib import Path

# ReelHaven's own folders inside a library (ADR-0016); never browsed or scanned.
INTERNAL_DIR = ".reelhaven"


class PathNotAllowedError(ValueError):
    """The path is outside the allowed root, missing, or otherwise unusable."""


def resolve_within(root: Path, user_path: str | Path, *, must_exist: bool = True) -> Path:
    """Resolve ``user_path`` (relative to ``root``, or absolute) inside ``root``.

    Raises PathNotAllowedError if the real path escapes ``root``, passes
    through a ``.reelhaven`` folder, or doesn't exist (when ``must_exist``).
    """
    text = str(user_path)
    if "\x00" in text:
        raise PathNotAllowedError("invalid path")
    real_root = root.resolve(strict=True)
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = real_root / candidate
    try:
        real = candidate.resolve(strict=must_exist)
    except (FileNotFoundError, NotADirectoryError):
        raise PathNotAllowedError("path does not exist") from None
    except (OSError, RuntimeError):  # permission errors, symlink loops
        raise PathNotAllowedError("path can't be read") from None
    if real != real_root and not real.is_relative_to(real_root):
        raise PathNotAllowedError("path is outside the media folder")
    if INTERNAL_DIR in real.relative_to(real_root).parts:
        raise PathNotAllowedError("ReelHaven's own folders can't be used")
    return real


def overlaps(a: Path, b: Path) -> bool:
    """True if one folder is the same as, or inside, the other."""
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)
