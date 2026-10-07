"""WebSocket with live job progress (ARCHITECTURE.md §11.1, SECURITY.md).

The server pushes a snapshot of the running jobs and the queue counts whenever
a job changes (at most twice a second) and every 15 seconds otherwise. The
client never sends anything that matters.
"""

import asyncio
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from reelhaven.api.deps import SESSION_COOKIE
from reelhaven.api.job_routes import job_out
from reelhaven.auth import network, security_settings, sessions
from reelhaven.db import Database, Job, Library
from reelhaven.live import ChangeFeed

router = APIRouter()

MIN_INTERVAL_S = 0.5  # progress arrives several times a second per job; coalesce it
HEARTBEAT_S = 15.0  # refreshes time-left estimates and keeps proxies from closing the socket
RECHECK_S = 30.0  # how soon a logout or expired session ends the socket
POLICY_VIOLATION = 1008


def _allowed(db: Database, websocket: WebSocket) -> bool:
    """A valid session cookie (not the API key or local bypass) from this site's own pages."""
    token = websocket.cookies.get(SESSION_COOKIE)
    if not token:
        return False
    with db.read() as session:
        trusted = network.parse_networks(security_settings.load(session).trusted_proxies)
        socket_ip = websocket.client.host if websocket.client else None
        headers = websocket.headers
        if not network.same_origin(
            headers.get("origin"),
            headers.get("host"),
            socket_ip,
            headers.get("x-forwarded-host"),
            trusted,
        ):
            return False
        return sessions.find(session, token) is not None


def _session_alive(db: Database, token: str) -> bool:
    with db.read() as session:
        return sessions.find(session, token) is not None


def snapshot(db: Database) -> dict[str, Any]:
    with db.read() as session:
        counts = dict(session.execute(select(Job.status, func.count()).group_by(Job.status)).all())
        rows = session.execute(
            select(Job, Library)
            .outerjoin(Library, Library.id == Job.library_id)
            .where(Job.status.in_(("running", "verifying")))
            .order_by(Job.id)
        ).all()
        active = [job_out(job, library, None).model_dump(mode="json") for job, library in rows]
    return {"type": "jobs", "counts": counts, "active": active}


async def _until_closed(websocket: WebSocket) -> None:
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        return


@router.websocket("/ws")
async def live(websocket: WebSocket) -> None:
    db: Database = websocket.app.state.db
    feed: ChangeFeed = websocket.app.state.live
    if not await run_in_threadpool(_allowed, db, websocket):
        # Before accept() this refuses the handshake (HTTP 403).
        await websocket.close(code=POLICY_VIOLATION)
        return
    token = websocket.cookies[SESSION_COOKIE]
    await websocket.accept()
    closed = asyncio.create_task(_until_closed(websocket))
    checked = time.monotonic()
    try:
        with feed.listen() as wake:
            while not closed.done():
                wake.clear()
                await websocket.send_json(await run_in_threadpool(snapshot, db))
                woken = asyncio.create_task(wake.wait())
                await asyncio.wait(
                    {closed, woken}, timeout=HEARTBEAT_S, return_when=asyncio.FIRST_COMPLETED
                )
                woken.cancel()
                if time.monotonic() - checked > RECHECK_S:
                    if not await run_in_threadpool(_session_alive, db, token):
                        await websocket.close(code=POLICY_VIOLATION)
                        return
                    checked = time.monotonic()
                if not closed.done():
                    await asyncio.sleep(MIN_INTERVAL_S)
    except (WebSocketDisconnect, RuntimeError):
        return  # the client went away mid-send
    finally:
        closed.cancel()
