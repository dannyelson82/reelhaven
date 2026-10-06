import json
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from reelhaven.app import create_app
from reelhaven.config import Settings
from reelhaven.db import Database, Integration, Library, MediaFile, Title
from reelhaven.db.types import utcnow
from reelhaven.resolver import LanguageResolver, assign_titles
from reelhaven.scanner import ScanProgress
from reelhaven.secretbox import SecretBox
from tests.helpers import API, admin_client

SERIES = [
    {
        "title": "Breaking Bad",
        "path": "/tv/Breaking Bad",
        "originalLanguage": {"id": 1, "name": "English"},
    },
    {"title": "Dark", "path": "/tv/Dark", "originalLanguage": {"id": 4, "name": "German"}},
    {"title": "Odd", "path": "/tv/Odd", "originalLanguage": None},
]
MOVIES = [
    {
        "title": "Amélie",
        "path": "D:\\Movies\\Amélie (2001)",
        "originalLanguage": {"name": "French"},
    },
]
TMDB_MOVIES = {
    "194": {"id": 194, "title": "Amélie", "original_language": "fr"},
    "550": {"id": 550, "title": "Fight Club", "original_language": "en"},
}


class FakeServices:
    def __init__(self) -> None:
        self.down: set[str] = set()
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        self.calls.append(f"{host}{path}")
        if host in self.down:
            raise httpx.ConnectError("down", request=request)
        if host == "sonarr" and path == "/api/v3/series":
            return httpx.Response(200, json=SERIES)
        if host == "radarr" and path == "/api/v3/movie":
            return httpx.Response(200, json=MOVIES)
        if host == "api.themoviedb.org":
            params = parse_qs(request.url.query.decode())
            if path.startswith("/3/movie/"):
                movie = TMDB_MOVIES.get(path.rsplit("/", 1)[1])
                return httpx.Response(200 if movie else 404, json=movie or {})
            if path == "/3/find/tt0137523":
                return httpx.Response(
                    200, json={"movie_results": [TMDB_MOVIES["550"]], "tv_results": []}
                )
            if path == "/3/search/movie":
                query = params["query"][0]
                results = {
                    "Spirited Away": [
                        {
                            "id": 129,
                            "title": "Spirited Away",
                            "original_title": "千と千尋の神隠し",
                            "release_date": "2001-07-20",
                            "original_language": "ja",
                        },
                    ],
                    "Solaris": [
                        {
                            "id": 1,
                            "title": "Solaris",
                            "release_date": "1972-03-20",
                            "original_language": "ru",
                        },
                        {
                            "id": 2,
                            "title": "Solaris",
                            "release_date": "2002-11-27",
                            "original_language": "en",
                        },
                    ],
                    "Close Enough": [
                        {
                            "id": 3,
                            "title": "Close Enough Movie",
                            "release_date": "2010-01-01",
                            "original_language": "en",
                        },
                    ],
                }.get(query, [])
                year = params.get("year", [None])[0]
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            r
                            for r in results
                            if not year or str(r["release_date"]).startswith(year)
                        ]
                    },
                )
        return httpx.Response(404, json={})


@pytest.fixture
def services() -> FakeServices:
    return FakeServices()


@pytest.fixture
def box(settings: Settings) -> SecretBox:
    return SecretBox(settings.config_dir)


def add_integration(db: Database, box: SecretBox, kind: str, url: str, **extra: Any) -> None:
    with db.write() as session:
        session.add(
            Integration(
                kind=kind,
                name=kind.title(),
                base_url=url,
                api_key_encrypted=box.encrypt("k" * 32),
                path_mappings=extra.pop("path_mappings", []),
                **extra,
            )
        )


def add_library(db: Database, name: str, type_: str, path: str, files: list[str]) -> int:
    with db.write() as session:
        library = Library(name=name, type=type_, path=path)
        session.add(library)
        session.flush()
        for i, rel in enumerate(files):
            session.add(
                MediaFile(
                    library_id=library.id,
                    path=f"{path}/{rel}",
                    relative_path=rel,
                    size=1,
                    mtime_ns=i,
                    fingerprint=f"1:{i}:x",
                    status="ok",
                )
            )
        return library.id


def titles(db: Database, library_id: int) -> dict[str, Title]:
    with db.read() as session:
        return {
            t.folder: t
            for t in session.scalars(select(Title).where(Title.library_id == library_id))
        }


def test_assign_titles_groups_episodes(db: Database) -> None:
    lib = add_library(
        db, "TV", "tv", "/media/TV", ["Dark/S01/e1.mkv", "Dark/S01/e2.mkv", "Odd/e1.mkv"]
    )
    assign_titles(db, lib)
    found = titles(db, lib)
    assert set(found) == {"Dark", "Odd"}
    with db.read() as session:
        assert {f.title_id for f in session.scalars(select(MediaFile))} == {
            found["Dark"].id,
            found["Odd"].id,
        }


def test_sonarr_with_path_mapping(db: Database, box: SecretBox, services: FakeServices) -> None:
    add_integration(
        db,
        box,
        "sonarr",
        "http://sonarr:8989",
        path_mappings=[{"remote": "/tv", "local": "/media/TV"}],
    )
    lib = add_library(
        db,
        "TV",
        "tv",
        "/media/TV",
        ["Breaking Bad/Season 1/e1.mkv", "Dark/e1.mkv", "Odd/e1.mkv", "Unknown Show/e1.mkv"],
    )
    summary = LanguageResolver(db, box, httpx.MockTransport(services)).resolve_library(lib)
    found = titles(db, lib)
    assert (found["Breaking Bad"].original_language, found["Breaking Bad"].language_source) == (
        "eng",
        "sonarr",
    )
    assert found["Breaking Bad"].source_detail == "Sonarr: Breaking Bad"
    assert found["Dark"].original_language == "deu"
    assert (found["Odd"].original_language, found["Odd"].language_source) == (None, "unknown")
    assert found["Unknown Show"].language_source == "unknown"
    assert (summary.resolved, summary.unknown, summary.errors) == (2, 2, [])


def test_radarr_windows_paths(db: Database, box: SecretBox, services: FakeServices) -> None:
    add_integration(
        db,
        box,
        "radarr",
        "http://radarr:7878",
        path_mappings=[{"remote": "D:\\Movies", "local": "/media/Movies"}],
    )
    lib = add_library(db, "Movies", "movies", "/media/Movies", ["Amélie (2001)/Amélie.mkv"])
    LanguageResolver(db, box, httpx.MockTransport(services)).resolve_library(lib)
    assert titles(db, lib)["Amélie (2001)"].original_language == "fra"


def test_tmdb_fallback(db: Database, box: SecretBox, services: FakeServices) -> None:
    add_integration(db, box, "tmdb", "https://api.themoviedb.org")
    lib = add_library(
        db,
        "Movies",
        "movies",
        "/media/Movies",
        [
            "Whatever {tmdb-194}/a.mkv",
            "Fight Club [imdbid-tt0137523]/f.mkv",
            "Spirited Away (2001)/s.mkv",
            "Solaris/s.mkv",  # two exact matches, no year: ambiguous
            "Solaris (2002)/s.mkv",  # year decides
            "Close Enough (2010)/c.mkv",  # not an exact title: no guess
        ],
    )
    LanguageResolver(db, box, httpx.MockTransport(services)).resolve_library(lib)
    found = {k: (t.original_language, t.language_source) for k, t in titles(db, lib).items()}
    assert found == {
        "Whatever {tmdb-194}": ("fra", "tmdb"),
        "Fight Club [imdbid-tt0137523]": ("eng", "tmdb"),
        "Spirited Away (2001)": ("jpn", "tmdb"),
        "Solaris": (None, "unknown"),
        "Solaris (2002)": ("eng", "tmdb"),
        "Close Enough (2010)": (None, "unknown"),
    }


def test_arr_wins_over_tmdb(db: Database, box: SecretBox, services: FakeServices) -> None:
    add_integration(
        db,
        box,
        "sonarr",
        "http://sonarr:8989",
        path_mappings=[{"remote": "/tv", "local": "/media/TV"}],
    )
    add_integration(db, box, "tmdb", "https://api.themoviedb.org")
    lib = add_library(db, "TV", "tv", "/media/TV", ["Dark/e1.mkv"])
    LanguageResolver(db, box, httpx.MockTransport(services)).resolve_library(lib)
    assert not any("themoviedb" in c for c in services.calls)


def test_manual_override_and_refresh_rules(
    db: Database, box: SecretBox, services: FakeServices
) -> None:
    add_integration(
        db,
        box,
        "sonarr",
        "http://sonarr:8989",
        path_mappings=[{"remote": "/tv", "local": "/media/TV"}],
    )
    lib = add_library(db, "TV", "tv", "/media/TV", ["Dark/e1.mkv", "Odd/e1.mkv"])
    resolver = LanguageResolver(db, box, httpx.MockTransport(services))
    resolver.resolve_library(lib)
    with db.write() as session:
        session.execute(
            update(Title)
            .where(Title.folder == "Dark")
            .values(original_language="eng", language_source="manual")
        )
    # Recently resolved and manual titles aren't looked up again...
    assert resolver.resolve_library(lib).titles == 0
    # ...a forced refresh re-checks everything except manual overrides.
    summary = resolver.resolve_library(lib, force=True)
    assert summary.titles == 1
    assert titles(db, lib)["Dark"].original_language == "eng"
    # Unknown titles are retried after a day.
    with db.write() as session:
        session.execute(
            update(Title)
            .where(Title.folder == "Odd")
            .values(resolved_at=utcnow() - timedelta(days=2))
        )
    assert resolver.resolve_library(lib).titles == 1


def test_service_down_keeps_previous_answer(
    db: Database, box: SecretBox, services: FakeServices
) -> None:
    add_integration(
        db,
        box,
        "sonarr",
        "http://sonarr:8989",
        path_mappings=[{"remote": "/tv", "local": "/media/TV"}],
    )
    lib = add_library(db, "TV", "tv", "/media/TV", ["Dark/e1.mkv"])
    resolver = LanguageResolver(db, box, httpx.MockTransport(services))
    resolver.resolve_library(lib)
    services.down.add("sonarr")
    summary = resolver.resolve_library(lib, force=True)
    assert summary.errors and "Sonarr" in summary.errors[0]
    # An outage must not wipe a known language.
    assert titles(db, lib)["Dark"].original_language == "deu"
    assert titles(db, lib)["Dark"].language_source == "sonarr"


def test_disabled_integration_ignored(db: Database, box: SecretBox, services: FakeServices) -> None:
    add_integration(
        db,
        box,
        "sonarr",
        "http://sonarr:8989",
        enabled=False,
        path_mappings=[{"remote": "/tv", "local": "/media/TV"}],
    )
    lib = add_library(db, "TV", "tv", "/media/TV", ["Dark/e1.mkv"])
    LanguageResolver(db, box, httpx.MockTransport(services)).resolve_library(lib)
    assert services.calls == []


# --- API ----------------------------------------------------------------------------


@pytest.fixture
def app(settings: Settings, services: FakeServices) -> Iterator[FastAPI]:
    application = create_app(settings, gateways=frozenset())
    application.state.http_transport = httpx.MockTransport(services)
    with TestClient(application):
        yield application


def test_titles_api_and_override(app: FastAPI) -> None:
    admin = admin_client(app)
    db: Database = app.state.db
    lib = add_library(
        db, "Movies", "movies", "/media/Movies", ["Amélie (2001)/a.mkv", "Amélie (2001)/b.mkv"]
    )
    progress = ScanProgress(lib)
    app.state.scanner.languages(lib, progress)  # no integrations: everything unknown
    assert progress.languages_unknown == 1

    page = admin.get(f"{API}/libraries/{lib}/titles").json()
    title = page["items"][0]
    assert (title["name"], title["year"], title["file_count"]) == ("Amélie", 2001, 2)
    assert admin.get(f"{API}/libraries/{lib}/titles", params={"unknown": True}).json()["total"] == 1

    assert (
        admin.put(
            f"{API}/titles/{title['id']}/language", json={"language": "not-a-language"}
        ).status_code
        == 422
    )
    done = admin.put(f"{API}/titles/{title['id']}/language", json={"language": "French"}).json()
    assert done == {"original_language": "fra", "language_source": "manual"}
    files = admin.get(f"{API}/libraries/{lib}/files").json()["items"]
    assert {f["original_language"] for f in files} == {"fra"}

    cleared = admin.put(f"{API}/titles/{title['id']}/language", json={"language": None}).json()
    assert cleared == {"original_language": None, "language_source": "unknown"}

    languages = admin.get(f"{API}/languages").json()
    assert {"code": "fra", "name": "French"} in languages
    assert all(len(lang["code"]) == 3 for lang in languages)

    assert admin.post(f"{API}/libraries/{lib}/languages/refresh").json() == {"started": True}
    app.state.scanner.wait(lib, timeout=30)
    status = admin.get(f"{API}/libraries/{lib}/scan").json()
    assert status["state"] == "done"
    assert json.dumps(status)  # serialisable, includes language fields
    assert status["languages_unknown"] == 1
