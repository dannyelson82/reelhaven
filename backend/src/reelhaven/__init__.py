"""ReelHaven: automatic, language-aware video library compression."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("reelhaven")
except PackageNotFoundError:  # pragma: no cover - only when run from a bare source tree
    __version__ = "0.0.0"
