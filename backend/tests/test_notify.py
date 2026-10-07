"""Telling Plex, Sonarr and Radarr about replaced files (ADR-0025)."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from reelhaven import settings_store
from reelhaven.db import Database, Integration, Job, JobResult, Library
from reelhaven.db.types import utcnow
from reelhaven.integrations.clients import IntegrationError, PlexClient
from reelhaven.notify import Notifier, NotifyStatus, arr_targets, plex_targets, status_key
from reelhaven.secretbox import SecretBox

PLEX_TOKEN = "plex-token-123"
SONARR_KEY = "a" * 32


def test_plex_targets() -> None:
    sections = [("1", ["/data/movies"]), ("2", ["/data/tv", "/data/tv-kids"])]
    folders = ["/data/tv/Show/Season 01", "/data/tv-kids/Cartoon", "/elsewhere/x", "/data/tv"]
    assert plex_targets(folders, sections) == {
        ("2", "/data/tv/Show/Season 01"),
        ("2", "/data/tv-kids/Cartoon"),
        ("2", "/data/tv"),
    }


def test_arr_targets() -> None:
    titles: list[dict[str, Any]] = [
        {"id": 7, "path": "/tv/Show"},
        {"id": 8, "path": "/tv/Show 2"},  # a prefix look-alike
        {"id": "x", "path": "/tv/Bad"},
        {"id": 9},
    ]
    assert arr_targets(["/tv/Show/Season 01", "/tv/Show/Season 02"], titles) == {7}
    assert arr_targets(["/tv/Other"], titles) == set()


Calls = list[tuple[str, str, dict[str, Any]]]


def fake_servers(calls: Calls, *, plex_ok: bool = True) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        body = json.loads(request.content) if request.content else {}
        calls.append((request.method, f"{request.url.host}{request.url.path}", {**params, **body}))
        if request.url.host == "plex":
            if request.headers.get("X-Plex-Token") != PLEX_TOKEN or not plex_ok:
                return httpx.Response(401)
            if request.url.path == "/identity":
                return httpx.Response(
                    200, json={"MediaContainer": {"machineIdentifier": "abc", "version": "1.41"}}
                )
            if request.url.path == "/library/sections":
                return httpx.Response(
                    200,
                    json={
                        "MediaContainer": {
                            "Directory": [
                                {"key": "1", "Location": [{"path": "/data/movies"}]},
                                {"key": "2", "Location": [{"path": "/data/tv"}]},
                            ]
                        }
                    },
                )
            if request.url.path.endswith("/refresh"):
                return httpx.Response(200)
        if request.url.host == "sonarr":
            if request.headers.get("X-Api-Key") != SONARR_KEY:
                return httpx.Response(401)
            if request.url.path == "/api/v3/series":
                return httpx.Response(200, json=[{"id": 7, "path": "/tv/Show"}])
            if request.url.path == "/api/v3/command":
                return httpx.Response(201, json={"id": 1, "name": body.get("name")})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_plex_client() -> None:
    calls: Calls = []
    plex = PlexClient("http://plex:32400", PLEX_TOKEN, transport=fake_servers(calls))
    assert plex.test() == {"app": "Plex", "version": "1.41"}
    wrong = PlexClient("http://plex:32400", "nope", transport=fake_servers(calls))
    with pytest.raises(IntegrationError) as info:
        wrong.test()
    assert info.value.code == "unauthorized"


def finished_job(db: Database, library_id: int, path: str) -> None:
    with db.write() as session:
        job = Job(
            library_id=library_id,
            type="remux",
            status="done",
            source_path=path,
            source_size=1,
            source_mtime_ns=1,
            plan={},
            probe={},
            requested_by="admin",
            finished_at=utcnow(),
        )
        session.add(job)
        session.flush()
        session.add(JobResult(job_id=job.id, bytes_before=2, bytes_after=1, process_seconds=1))


def test_notifier_batches_and_notifies(db: Database, tmp_path: Path) -> None:
    box = SecretBox(tmp_path)
    with db.write() as session:
        library = Library(name="TV", type="tv", path="/media/TV")
        session.add(library)
        session.flush()
        library_id = library.id
        plex = Integration(
            kind="plex",
            name="Plex",
            base_url="http://plex:32400",
            api_key_encrypted=box.encrypt(PLEX_TOKEN),
            path_mappings=[{"remote": "/data/tv", "local": "/media/TV"}],
        )
        sonarr = Integration(
            kind="sonarr",
            name="Sonarr",
            base_url="http://sonarr:8989",
            api_key_encrypted=box.encrypt(SONARR_KEY),
            path_mappings=[{"remote": "/tv", "local": "/media/TV"}],
        )
        session.add_all([plex, sonarr])
        session.flush()
        plex_id, sonarr_id = plex.id, sonarr.id
    calls: Calls = []
    transport = fake_servers(calls)
    notifier = Notifier(db, box=lambda: box, transport=lambda: transport)
    notifier.prime()
    assert notifier.flush() == 0 and calls == []  # nothing replaced yet

    # A season finishes: two episodes, one folder.
    for episode in (1, 2):
        finished_job(db, library_id, f"/media/TV/Show/Season 01/Show - S01E0{episode}.mkv")
    assert notifier.flush() == 1
    refreshes = [c for c in calls if c[1].endswith("/refresh")]
    assert refreshes == [
        ("GET", "plex/library/sections/2/refresh", {"path": "/data/tv/Show/Season 01"})
    ]
    commands = [c for c in calls if c[1] == "sonarr/api/v3/command"]
    assert commands == [("POST", "sonarr/api/v3/command", {"name": "RescanSeries", "seriesId": 7})]
    with db.read() as session:
        plex_status = NotifyStatus.model_validate(settings_store.get(session, status_key(plex_id)))
        sonarr_status = settings_store.get(session, status_key(sonarr_id))
    assert plex_status.ok and plex_status.message == "Asked to refresh 1 folder."
    assert sonarr_status and sonarr_status["message"] == "Asked to refresh 1 series."

    # Nothing new: nothing sent again.
    calls.clear()
    assert notifier.flush() == 0 and calls == []


def test_notifier_records_failures(db: Database, tmp_path: Path) -> None:
    box = SecretBox(tmp_path)
    with db.write() as session:
        library = Library(name="TV", type="tv", path="/media/TV")
        plex = Integration(
            kind="plex",
            name="Plex",
            base_url="http://plex:32400",
            api_key_encrypted=box.encrypt("wrong-token"),
        )
        session.add_all([library, plex])
        session.flush()
        library_id, plex_id = library.id, plex.id
    calls: Calls = []
    transport = fake_servers(calls)
    notifier = Notifier(db, box=lambda: box, transport=lambda: transport)
    notifier.prime()
    finished_job(db, library_id, "/media/TV/Show/x.mkv")
    assert notifier.flush() == 1
    with db.read() as session:
        status = NotifyStatus.model_validate(settings_store.get(session, status_key(plex_id)))
    assert not status.ok and status.message == "The API key was rejected"


def test_jobs_finished_before_a_restart_are_not_resent(db: Database, tmp_path: Path) -> None:
    box = SecretBox(tmp_path)
    with db.write() as session:
        library = Library(name="TV", type="tv", path="/media/TV")
        session.add(library)
        session.flush()
        library_id = library.id
    finished_job(db, library_id, "/media/TV/Old/x.mkv")
    with db.write() as session:
        for job in session.query(Job):
            job.finished_at = utcnow() - timedelta(hours=2)
    notifier = Notifier(db, box=lambda: box)
    notifier.prime()
    assert notifier.flush() == 0
