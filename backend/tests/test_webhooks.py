"""Sonarr/Radarr webhooks (ADR-0025)."""

from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from reelhaven.db import Database, Integration, Library
from reelhaven.webhooks import match_library, remote_paths
from tests.helpers import API, admin_client, client_at, csrf

# Shapes as Sonarr v4 / Radarr v5 send them (trimmed).
SONARR_IMPORT: dict[str, Any] = {
    "eventType": "Download",
    "isUpgrade": False,
    "series": {"id": 7, "title": "Show", "path": "/tv/Show"},
    "episodes": [{"id": 1, "seasonNumber": 1, "episodeNumber": 2}],
    "episodeFile": {"id": 3, "relativePath": "Season 01/Show - S01E02.mkv",
                    "path": "/tv/Show/Season 01/Show - S01E02.mkv"},
}  # fmt: skip
RADARR_IMPORT: dict[str, Any] = {
    "eventType": "Download",
    "movie": {"id": 4, "title": "Film", "folderPath": "/movies/Film (2020)"},
    "movieFile": {"id": 5, "relativePath": "Film.mkv", "path": "/movies/Film (2020)/Film.mkv"},
}


def test_remote_paths() -> None:
    assert remote_paths("sonarr", SONARR_IMPORT) == [
        "/tv/Show",
        "/tv/Show/Season 01/Show - S01E02.mkv",
    ]
    assert remote_paths("radarr", RADARR_IMPORT) == [
        "/movies/Film (2020)",
        "/movies/Film (2020)/Film.mkv",
    ]
    assert remote_paths("sonarr", {"eventType": "Download", "series": "nonsense"}) == []
    assert remote_paths("radarr", {"movie": {"folderPath": 12}, "movieFile": [1]}) == []


def test_match_library_uses_mappings_and_the_deepest_library() -> None:
    libraries = [(1, "/media/TV"), (2, "/media/Movies"), (3, "/media/TV/Kids")]
    tv_map = [{"remote": "/tv", "local": "/media/TV"}]
    assert match_library(["/tv/Show"], [tv_map], libraries) == (1, "/media/TV/Show")
    assert match_library(["/tv/Kids/Cartoon"], [tv_map], libraries) == (
        3,
        "/media/TV/Kids/Cartoon",
    )
    # Same paths on both sides: no mapping needed.
    assert match_library(["/media/Movies/Film"], [], libraries) == (2, "/media/Movies/Film")
    # Similar-looking prefixes don't count.
    assert match_library(["/media/TV2/Show"], [], libraries) is None
    # Several instances: whichever mapping fits.
    other = [{"remote": "/data/movies", "local": "/media/Movies"}]
    assert match_library(["/data/movies/Film"], [tv_map, other], libraries) == (
        2,
        "/media/Movies/Film",
    )


def api_key(admin: TestClient) -> str:
    created = admin.post(f"{API}/settings/security/api-key", headers=csrf(admin))
    return str(created.json()["api_key"])


def test_webhook_api(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    admin = admin_client(app)
    key = api_key(admin)
    db: Database = app.state.db
    with db.write() as session:
        session.add_all(
            [
                Library(name="TV", type="tv", path="/media/TV", watch_mode="automatic"),
                Library(name="Movies", type="movies", path="/media/Movies", watch_mode="off"),
                Integration(
                    kind="sonarr",
                    name="Sonarr",
                    base_url="http://s:8989",
                    api_key_encrypted="x",
                    path_mappings=[{"remote": "/tv", "local": "/media/TV"}],
                ),
            ]
        )
    changed: list[tuple[int, str | None]] = []
    app.state.watcher.changed = lambda library_id, folder=None: changed.append((library_id, folder))
    hook = client_at(app, "192.168.1.30")

    # No key, wrong key: refused.
    # Without a key it's refused (the CSRF check answers first).
    assert hook.post(f"{API}/webhook/sonarr", json=SONARR_IMPORT).status_code in (401, 403)
    assert hook.post(f"{API}/webhook/sonarr?apikey=nope", json=SONARR_IMPORT).status_code == 401
    assert hook.post(f"{API}/webhook/lidarr?apikey={key}", json={}).status_code == 422

    test = hook.post(f"{API}/webhook/sonarr?apikey={key}", json={"eventType": "Test"})
    assert test.status_code == 200 and test.json()["outcome"] == "test"

    imported = hook.post(f"{API}/webhook/sonarr?apikey={key}", json=SONARR_IMPORT).json()
    assert imported == {
        "outcome": "rescan",
        "message": "Show in TV will be rescanned shortly.",  # just that series (ADR-0030)
        "library": "TV",
    }
    with db.read() as session:
        tv_id = next(lib.id for lib in session.query(Library) if lib.name == "TV")
    assert changed == [(tv_id, "Show")]

    grab = hook.post(f"{API}/webhook/sonarr?apikey={key}", json={"eventType": "Grab"}).json()
    assert grab["outcome"] == "ignored"
    off = hook.post(f"{API}/webhook/radarr", json=RADARR_IMPORT, headers={"X-Api-Key": key}).json()
    assert off["outcome"] == "no_library"  # Radarr's /movies isn't mapped
    movies = {**RADARR_IMPORT, "movie": {"folderPath": "/media/Movies/Film (2020)"}}
    off = hook.post(f"{API}/webhook/radarr?apikey={key}", json=movies).json()
    assert (off["outcome"], off["library"]) == ("not_watched", "Movies")
    assert changed == [(tv_id, "Show")]  # Off libraries aren't rescanned

    bad = hook.post(
        f"{API}/webhook/sonarr?apikey={key}",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )
    assert bad.status_code == 422
    huge = hook.post(f"{API}/webhook/sonarr?apikey={key}", content=b" " * (1024 * 1024 + 1))
    assert huge.status_code == 413

    status = admin.get(f"{API}/webhooks").json()
    assert status["sonarr"]["event"] == "Grab" and status["sonarr"]["outcome"] == "ignored"
    assert status["radarr"]["outcome"] == "not_watched"
    assert status["radarr"]["library"] == "Movies"
