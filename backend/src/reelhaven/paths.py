"""File-system confinement (SECURITY.md "File system confinement").

Every path that comes from the UI, the API or a webhook goes through
``resolve_within`` before it is used. Symlinks are resolved *before* the
containment check, so a link can't point ReelHaven at other host folders.
"""

import os
from pathlib import Path

# ReelHaven's own folders inside a library (ADR-0016); never browsed or scanned.
INTERNAL_DIR = ".reelhaven"


class PathNotAllowedError(ValueError):
    """The path is outside the allowed root, missing, or otherwise unusable."""


def resolve_within(root: Path, user_path: str | Path, *, must_exist: bool = True) -> Path:
    """Resolve ``user_path`` (relative to ``root``, or absolute) inside ``root``.

    Raises PathNotAllowedError if the real path escapes ``root``, passes
    through a ``.reelhaven`` folder, or doesn't exist (when ``must_exist``).
    Written as realpath + prefix check, the pattern static analysers recognise.
    """
    text = os.fspath(user_path)
    if "\x00" in text:
        raise PathNotAllowedError("invalid path")
    real_root = os.path.realpath(root, strict=True)
    try:
        # os.path.join keeps ``text`` as-is when it is absolute.
        real = os.path.realpath(os.path.join(real_root, text), strict=must_exist)  # noqa: PTH118
    except (FileNotFoundError, NotADirectoryError):
        raise PathNotAllowedError("path does not exist") from None
    except OSError:  # permission errors, symlink loops
        raise PathNotAllowedError("path can't be read") from None
    if real != real_root and not real.startswith(real_root + os.sep):
        raise PathNotAllowedError("path is outside the media folder")
    relative = os.path.relpath(real, real_root)
    if INTERNAL_DIR in relative.split(os.sep):  # noqa: PTH206
        raise PathNotAllowedError("ReelHaven's own folders can't be used")
    return Path(real)


def overlaps(a: Path, b: Path) -> bool:
    """True if one folder is the same as, or inside, the other."""
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)
