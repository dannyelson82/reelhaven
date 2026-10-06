"""Path mapping: Sonarr may see a file as /tv/Show/x.mkv while ReelHaven
sees /media/TV/Show/x.mkv (ARCHITECTURE.md §6.9)."""

from pathlib import PurePosixPath


def _norm(path: str) -> str:
    return str(PurePosixPath(path.replace("\\", "/")))


def _apply(path: str, pairs: list[tuple[str, str]]) -> str | None:
    target = _norm(path)
    best: tuple[str, str] | None = None
    for source, dest in pairs:
        src = _norm(source)
        if (target == src or target.startswith(src.rstrip("/") + "/")) and (
            best is None or len(src) > len(best[0])
        ):
            best = (src, _norm(dest))
    if best is None:
        return None
    rest = target[len(best[0]) :].lstrip("/")
    return str(PurePosixPath(best[1]) / rest) if rest else best[1]


def to_local(remote_path: str, mappings: list[dict[str, str]]) -> str:
    """Translate a path reported by the service into ReelHaven's view.

    Without a matching mapping the path is returned unchanged (both sides may
    use the same paths).
    """
    mapped = _apply(remote_path, [(m["remote"], m["local"]) for m in mappings])
    return mapped if mapped is not None else _norm(remote_path)


def to_remote(local_path: str, mappings: list[dict[str, str]]) -> str:
    """Translate one of ReelHaven's paths into the service's view."""
    mapped = _apply(local_path, [(m["local"], m["remote"]) for m in mappings])
    return mapped if mapped is not None else _norm(local_path)
