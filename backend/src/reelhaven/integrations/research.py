"""Ask Sonarr/Radarr for a different release of a wrong-language file (ADR-0032).

For the file's episodes (Sonarr) or movie (Radarr): mark the grab that brought the file
as failed, which blocklists that release; remove the file's record; and search again.
API v3, as in Sonarr's and Radarr's published OpenAPI descriptions.
"""

import logging
from pathlib import PurePosixPath
from typing import Any

import httpx
from sqlalchemy import select

from reelhaven.db import Database, Integration
from reelhaven.integrations.clients import ArrClient, IntegrationError
from reelhaven.integrations.pathmap import to_remote
from reelhaven.integrations.service import client_for
from reelhaven.notify import arr_targets
from reelhaven.secretbox import SecretBox

logger = logging.getLogger(__name__)


def _latest_grab(history: Any, matches: set[int], key: str) -> int | None:
    """The newest 'grabbed' history entry for one of ``matches`` (episode or movie ids)."""
    grabs = [
        h
        for h in (history if isinstance(history, list) else [])
        if isinstance(h, dict)
        and str(h.get("eventType", "")).lower() == "grabbed"
        and h.get(key) in matches
        and isinstance(h.get("id"), int)
    ]
    if not grabs:
        return None
    newest = max(grabs, key=lambda h: (str(h.get("date", "")), h["id"]))
    return int(newest["id"])


def request_new_release(client: ArrClient, remote_path: str) -> str | None:
    """Blocklist the release behind ``remote_path`` (as Sonarr/Radarr sees it) and search
    for another. Returns what happened in plain words, or None if this server doesn't
    manage the file. Raises IntegrationError if the server can't be reached."""
    folder = str(PurePosixPath(remote_path).parent)
    ids = arr_targets([folder], client.titles())
    if not ids:
        return None
    item_id = min(ids)
    if client.kind == "sonarr":
        return _sonarr(client, item_id, remote_path)
    return _radarr(client, item_id, remote_path)


def _file_id(files: Any, remote_path: str) -> int | None:
    for f in files if isinstance(files, list) else []:
        if isinstance(f, dict) and f.get("path") == remote_path and isinstance(f.get("id"), int):
            return int(f["id"])
    return None


def _sonarr(client: ArrClient, series_id: int, remote_path: str) -> str:
    file_id = _file_id(client.get_json("/api/v3/episodefile", {"seriesId": series_id}), remote_path)
    if file_id is None:
        raise IntegrationError("not_found", "Sonarr doesn't know this file")
    episodes = client.get_json("/api/v3/episode", {"seriesId": series_id, "episodeFileId": file_id})
    episode_ids = {
        int(e["id"])
        for e in (episodes if isinstance(episodes, list) else [])
        if isinstance(e, dict) and isinstance(e.get("id"), int)
    }
    grab = _latest_grab(
        client.get_json("/api/v3/history/series", {"seriesId": series_id}),
        episode_ids,
        "episodeId",
    )
    if grab is not None:
        client.post(f"/api/v3/history/failed/{grab}")
    client.delete(f"/api/v3/episodefile/{file_id}")
    client.post("/api/v3/command", {"name": "EpisodeSearch", "episodeIds": sorted(episode_ids)})
    return (
        "Sonarr blocklisted that release and is searching for another."
        if grab is not None
        else "Sonarr is searching for another release (no download to blocklist)."
    )


def _radarr(client: ArrClient, movie_id: int, remote_path: str) -> str:
    file_id = _file_id(client.get_json("/api/v3/moviefile", {"movieId": movie_id}), remote_path)
    if file_id is None:
        raise IntegrationError("not_found", "Radarr doesn't know this file")
    grab = _latest_grab(
        client.get_json("/api/v3/history/movie", {"movieId": movie_id}), {movie_id}, "movieId"
    )
    if grab is not None:
        client.post(f"/api/v3/history/failed/{grab}")
    client.delete(f"/api/v3/moviefile/{file_id}")
    client.post("/api/v3/command", {"name": "MoviesSearch", "movieIds": [movie_id]})
    return (
        "Radarr blocklisted that release and is searching for another."
        if grab is not None
        else "Radarr is searching for another release (no download to blocklist)."
    )


def ask_for_new_release(
    db: Database,
    box: SecretBox,
    transport: httpx.BaseTransport | None,
    local_path: str,
) -> list[str]:
    """Ask every enabled Sonarr/Radarr that manages this file for another release.
    Returns one line per server that manages it (or failed to answer)."""
    with db.read() as session:
        servers = [
            (i.name, list(i.path_mappings or []), i)
            for i in session.scalars(
                select(Integration).where(
                    Integration.enabled, Integration.kind.in_(("sonarr", "radarr"))
                )
            )
        ]
    lines: list[str] = []
    for name, mappings, row in servers:
        try:
            with client_for(row, box, transport) as client:
                if not isinstance(client, ArrClient):
                    continue
                done = request_new_release(client, to_remote(local_path, mappings))
        except IntegrationError as exc:
            logger.warning("re-search failed", extra={"integration": name, "error": exc.message})
            lines.append(f"{name}: couldn't ask for another release ({exc.message}).")
            continue
        if done is not None:
            lines.append(f"{name}: {done}")
    if not lines:
        lines.append("No Sonarr or Radarr manages this file, so nothing was searched for.")
    return lines
