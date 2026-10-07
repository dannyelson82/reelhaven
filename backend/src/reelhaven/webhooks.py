"""Sonarr/Radarr webhooks (ADR-0025): which library a notification is about. Pure functions."""

from pathlib import PurePosixPath
from typing import Any, Literal

from reelhaven.integrations.pathmap import to_local

Kind = Literal["sonarr", "radarr"]

# Events after which the files on disk may have changed.
CHANGE_EVENTS = frozenset(
    {
        "Download",  # imported or upgraded
        "Rename",
        "EpisodeFileDelete",
        "SeriesDelete",
        "MovieFileDelete",
        "MovieDelete",
    }
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and 0 < len(value) <= 4096 else None


def remote_paths(kind: Kind, payload: dict[str, Any]) -> list[str]:
    """Folder and file paths named in the payload, as the service sees them."""
    paths: list[str | None] = []
    if kind == "sonarr":
        paths.append(_text(_dict(payload.get("series")).get("path")))
        files = payload.get("episodeFiles") or [payload.get("episodeFile")]
    else:
        paths.append(_text(_dict(payload.get("movie")).get("folderPath")))
        files = payload.get("movieFiles") or [payload.get("movieFile")]
    for item in files if isinstance(files, list) else []:
        if isinstance(item, dict):
            paths.append(_text(item.get("path")))
    return [p for p in paths if p]


def _norm(path: str) -> PurePosixPath:
    return PurePosixPath(path.replace("\\", "/"))


def match_library(
    remote: list[str],
    mappings: list[list[dict[str, str]]],
    libraries: list[tuple[int, str]],
) -> tuple[int, str] | None:
    """(library id, local path) for the first path that falls inside a library.

    Each integration of the right kind contributes its path mappings; a path is
    also tried unmapped, for setups where both apps see the same paths. The
    deepest matching library wins (libraries can't overlap, but be safe).
    """
    candidates: list[str] = []
    for path in remote:
        for mapping in [*mappings, []]:
            local = to_local(path, mapping)
            if local not in candidates:
                candidates.append(local)
    for local in candidates:
        target = _norm(local)
        found = [
            (library_id, root)
            for library_id, root in libraries
            if target == _norm(root) or _norm(root) in target.parents
        ]
        if found:
            library_id, _root = max(found, key=lambda item: len(item[1]))
            return library_id, local
    return None
