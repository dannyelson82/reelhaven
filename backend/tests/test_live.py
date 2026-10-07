import asyncio
import threading
from datetime import timedelta
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from reelhaven.api import live_routes
from reelhaven.db import Database, Job, Library
from reelhaven.db.types import utcnow
from reelhaven.live import ChangeFeed, eta_seconds
from tests.helpers import API, admin_client, client_at, csrf


def test_eta() -> None:
    assert eta_seconds(0.5, 600) == 600
    assert eta_seconds(0.25, 100) == 300
    assert eta_seconds(0.01, 600) is None  # too early to tell
    assert eta_seconds(0.5, 5) is None
    assert eta_seconds(1.0, 600) is None
    assert eta_seconds(0.0, 600) is None


def test_feed_wakes_listeners_from_other_threads() -> None:
    feed = ChangeFeed()

    async def main() -> bool:
        with feed.listen() as wake:
            threading.Thread(target=feed.changed).start()
            await asyncio.wait_for(wake.wait(), timeout=5)
        feed.changed()  # nobody listening any more: nothing happens
        return wake.is_set()

    assert asyncio.run(main())


def test_feed_survives_a_closed_loop() -> None:
    feed = ChangeFeed()
    loop = asyncio.new_event_loop()

    async def register() -> None:
        feed._listeners.add((asyncio.get_running_loop(), asyncio.Event()))

    loop.run_until_complete(register())
    loop.close()
    feed.changed()  # must not raise


ORIGIN = {"origin": "http://testserver"}


def add_job(app: FastAPI, status: str = "queued", **fields: object) -> int:
    db: Database = app.state.db
    with db.write() as session:
        library = session.scalars(select(Library)).first()
        if library is None:
            library = Library(name="Movies", type="movies", path="/media/Movies")
            session.add(library)
            session.flush()
        job = Job(
            library_id=library.id,
            type="encode",
            status=status,
            source_path="/media/Movies/Film (2020)/film.mkv",
            source_size=1,
            source_mtime_ns=1,
            plan={},
            probe={},
            requested_by="admin",
            **fields,
        )
        session.add(job)
        session.flush()
        return job.id


def set_job(app: FastAPI, job_id: int, **fields: object) -> None:
    db: Database = app.state.db
    with db.write() as session:
        job = session.get(Job, job_id)
        assert job is not None
        for key, value in fields.items():
            setattr(job, key, value)


def test_live_updates(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    app.state.queue.stop()  # nothing should pick up the fake jobs
    admin = admin_client(app)
    with admin.websocket_connect(f"{API}/ws", headers=ORIGIN) as ws:
        first = ws.receive_json()
        assert first == {"type": "jobs", "counts": {}, "active": []}

        job_id = add_job(app)
        assert ws.receive_json()["counts"] == {"queued": 1}

        started = utcnow() - timedelta(seconds=100)
        set_job(app, job_id, status="running", progress=0.25, fps=48.0, started_at=started)
        update = ws.receive_json()
        assert update["counts"] == {"running": 1}
        (active,) = update["active"]
        assert active["id"] == job_id and active["file"] == "Film (2020)/film.mkv"
        assert active["progress"] == 0.25 and active["fps"] == 48.0
        assert 290 <= active["eta_seconds"] <= 310

        set_job(app, job_id, status="done")
        assert ws.receive_json() == {"type": "jobs", "counts": {"done": 1}, "active": []}


def test_changes_are_coalesced(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    app.state.queue.stop()
    admin = admin_client(app)
    job_id = add_job(app, status="running", started_at=utcnow())
    with admin.websocket_connect(f"{API}/ws", headers=ORIGIN) as ws:
        ws.receive_json()
        for step in range(1, 11):
            set_job(app, job_id, progress=step / 10)
        seen = [ws.receive_json()["active"][0]["progress"]]
        while seen[-1] != 1.0:
            seen.append(ws.receive_json()["active"][0]["progress"])
        assert len(seen) < 10  # ten quick changes, fewer messages


def test_refused_without_a_session_or_from_another_site(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    admin = admin_client(app)
    for headers in ({"origin": "http://evil.example"}, {}):
        with (
            pytest.raises(WebSocketDisconnect) as refused,
            admin.websocket_connect(f"{API}/ws", headers=headers),
        ):
            pass
        assert refused.value.code == 1008
    stranger = client_at(app)
    with (
        pytest.raises(WebSocketDisconnect),
        stranger.websocket_connect(f"{API}/ws", headers=ORIGIN),
    ):
        pass


def test_logout_ends_the_socket(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live_routes, "RECHECK_S", 0.0)
    monkeypatch.setattr(live_routes, "HEARTBEAT_S", 0.2)
    app = cast(FastAPI, client.app)
    admin = admin_client(app)
    with admin.websocket_connect(f"{API}/ws", headers=ORIGIN) as ws:
        ws.receive_json()
        assert admin.post(f"{API}/auth/logout", headers=csrf(admin)).status_code == 204
        with pytest.raises(WebSocketDisconnect) as closed:
            while True:
                ws.receive_json()
        assert closed.value.code == 1008
