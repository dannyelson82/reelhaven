"""Wrong-language files (ADR-0032): quarantine or delete, and ask for another release."""

import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from reelhaven.automation import FileState, pick_wrong_language
from reelhaven.config import Settings
from reelhaven.db import RecycleItem
from reelhaven.dryrun import FilePlan
from reelhaven.integrations.clients import ArrClient
from reelhaven.integrations.research import request_new_release
from reelhaven.planner import Plan
from tests.helpers import API
from tests.media_fixtures import FFMPEG, Audio, Spec
from tests.test_remux import app, setup_library  # noqa: F401 - shared fixture

ffmpeg = pytest.mark.skipif(
    FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed"
)


class FakeArr:
    """Just enough Sonarr/Radarr (API v3) to follow what ReelHaven asks."""

    def __init__(self, kind: str, history: list[dict[str, Any]]) -> None:
        self.kind = kind
        self.history = history
        self.calls: list[tuple[str, str, Any]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body or dict(request.url.params)))
        path = request.url.path
        if path in ("/api/v3/series", "/api/v3/movie"):
            return httpx.Response(
                200, json=[{"id": 7, "path": "/tv/Show"}, {"id": 8, "path": "/tv/Other"}]
            )
        if path == "/api/v3/episodefile":
            return httpx.Response(200, json=[{"id": 31, "path": "/tv/Show/S01/e1.mkv"}])
        if path == "/api/v3/moviefile":
            return httpx.Response(200, json=[{"id": 41, "path": "/tv/Show/S01/e1.mkv"}])
        if path == "/api/v3/episode":
            return httpx.Response(200, json=[{"id": 101}, {"id": 102}])
        if path in ("/api/v3/history/series", "/api/v3/history/movie"):
            return httpx.Response(200, json=self.history)
        return httpx.Response(200, text="")

    def client(self) -> ArrClient:
        return ArrClient(
            self.kind,  # type: ignore[arg-type]
            "http://arr.local",
            "key",
            transport=httpx.MockTransport(self.handle),
        )


def _writes(fake: FakeArr) -> list[tuple[str, str, Any]]:
    return [c for c in fake.calls if c[0] != "GET"]


def test_sonarr_blocklists_the_grab_and_searches_the_episodes() -> None:
    fake = FakeArr(
        "sonarr",
        [
            {"id": 1, "episodeId": 101, "eventType": "grabbed", "date": "2026-01-01T00:00:00Z"},
            {"id": 2, "episodeId": 101, "eventType": "grabbed", "date": "2026-03-01T00:00:00Z"},
            {
                "id": 3,
                "episodeId": 101,
                "eventType": "downloadFolderImported",
                "date": "2026-03-02",
            },
            {"id": 4, "episodeId": 999, "eventType": "grabbed", "date": "2026-04-01T00:00:00Z"},
        ],
    )
    with fake.client() as client:
        said = request_new_release(client, "/tv/Show/S01/e1.mkv")
    assert said == "Sonarr blocklisted that release and is searching for another."
    assert _writes(fake) == [
        ("POST", "/api/v3/history/failed/2", {}),  # the newest grab of this episode
        ("DELETE", "/api/v3/episodefile/31", {}),
        ("POST", "/api/v3/command", {"name": "EpisodeSearch", "episodeIds": [101, 102]}),
    ]
    assert ("GET", "/api/v3/episode", {"seriesId": "7", "episodeFileId": "31"}) in fake.calls


def test_radarr_without_a_grab_still_searches() -> None:
    fake = FakeArr("radarr", [{"id": 5, "movieId": 7, "eventType": "movieFolderImported"}])
    with fake.client() as client:
        said = request_new_release(client, "/tv/Show/S01/e1.mkv")
    assert said == "Radarr is searching for another release (no download to blocklist)."
    assert _writes(fake) == [
        ("DELETE", "/api/v3/moviefile/41", {}),
        ("POST", "/api/v3/command", {"name": "MoviesSearch", "movieIds": [7]}),
    ]


def test_a_file_the_server_doesnt_manage() -> None:
    fake = FakeArr("sonarr", [])
    with fake.client() as client:
        assert request_new_release(client, "/movies/Film/film.mkv") is None
    assert _writes(fake) == []


def _plan(file_id: int, flags: list[str], pending: bool = False) -> FilePlan:
    plan = Plan(action="skip", tracks=[], flags=flags, summary="", details=[], removed_bytes=0)  # type: ignore[arg-type]
    return FilePlan(file_id, f"f{file_id}.mkv", 1, "eng", plan, pending)


def test_pick_wrong_language() -> None:
    plans = [
        _plan(1, ["wrong_language"]),
        _plan(2, ["no_wanted_audio"]),  # unsure: always waits for the owner
        _plan(3, ["wrong_language"], pending=True),
        _plan(4, ["wrong_language"]),  # already being handled
        _plan(5, ["wrong_language"]),  # failed before, unchanged since
        _plan(6, ["wrong_language"]),
        _plan(7, ["wrong_language"]),
    ]
    state = FileState(1, 1)
    chosen = pick_wrong_language(plans, active={4}, gave_up={5: state}, current={5: state}, limit=2)
    assert [p.file_id for p in chosen] == [1, 6]


@ffmpeg
def test_quarantine_and_delete(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    spanish = Spec(audio=[Audio("spa", default=True)])
    admin, lib, root = setup_library(
        app,
        settings,
        {"A (2020)/a.mkv": spanish, "B (2021)/b.mkv": spanish, "C (2022)/c.mkv": Spec()},
    )
    files = {
        f["relative_path"]: f["id"]
        for f in admin.get(f"{API}/libraries/{lib}/files").json()["items"]
    }
    review = admin.get(f"{API}/review", params={"kind": "wrong_language"}).json()
    assert sorted(i["relative_path"] for i in review["items"]) == [
        "A (2020)/a.mkv",
        "B (2021)/b.mkv",
    ]

    # Only wrong-language files can be moved aside this way.
    refused = admin.post(
        f"{API}/files/{files['C (2022)/c.mkv']}/wrong-language", json={"action": "delete"}
    )
    assert refused.status_code == 409 and refused.json()["detail"] == "not_wrong_language"

    started = admin.post(
        f"{API}/files/{files['A (2020)/a.mkv']}/wrong-language", json={"action": "quarantine"}
    )
    assert started.status_code == 201, started.text
    admin.post(f"{API}/files/{files['B (2021)/b.mkv']}/wrong-language", json={"action": "delete"})
    assert app.state.queue.wait_idle(60)

    assert not (root / "A (2020)/a.mkv").exists() and not (root / "B (2021)/b.mkv").exists()
    with app.state.db.read() as session:
        items = {i.reason: i for i in session.scalars(select(RecycleItem))}
    assert set(items) == {"quarantine", "wrong-language"}
    quarantined = items["quarantine"]
    assert quarantined.stored_path.startswith(str(root / ".reelhaven" / "recycle"))
    assert Path(quarantined.stored_path).exists()
    jobs = [j for j in admin.get(f"{API}/jobs").json()["items"] if j["type"] == "wrong_language"]
    assert {j["status"] for j in jobs} == {"done"}
    assert any("No Sonarr or Radarr manages this file" in d for d in jobs[0]["details"])
    # Gone from the library and from the review page; restorable like any recycled file.
    assert [
        f["relative_path"] for f in admin.get(f"{API}/libraries/{lib}/files").json()["items"]
    ] == ["C (2022)/c.mkv"]
    assert admin.get(f"{API}/review", params={"kind": "wrong_language"}).json()["total"] == 0
    assert admin.post(f"{API}/recycle/{quarantined.id}/restore").status_code == 200
    assert (root / "A (2020)/a.mkv").exists()


@ffmpeg
def test_automatic_libraries_act_on_their_own(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, root = setup_library(
        app, settings, {"A (2020)/a.mkv": Spec(audio=[Audio("spa", default=True)])}
    )
    policy = admin.get(f"{API}/libraries/{lib}/policy").json()
    assert (
        admin.put(
            f"{API}/libraries/{lib}/policy", json={**policy, "wrong_language_action": "quarantine"}
        ).status_code
        == 200
    )
    admin.patch(f"{API}/libraries/{lib}", json={"watch_mode": "watch"})
    assert app.state.automation.top_up(lib) == 0  # only automatic libraries act
    admin.patch(f"{API}/libraries/{lib}", json={"watch_mode": "automatic"})
    seen: list[str] = []

    def research(path: str) -> list[str]:
        seen.append(path)
        return ["asked"]

    app.state.queue.research = research
    assert app.state.automation.top_up(lib) == 1
    app.state.queue.notify()
    assert app.state.queue.wait_idle(60)
    assert not (root / "A (2020)/a.mkv").exists()
    assert seen == [str((root / "A (2020)/a.mkv").resolve())]
