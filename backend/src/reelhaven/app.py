"""FastAPI application factory."""

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from reelhaven import __version__
from reelhaven.api import (
    auth_routes,
    device_routes,
    file_routes,
    integration_routes,
    job_routes,
    library_routes,
    live_routes,
    profile_routes,
    security_routes,
    test_run_routes,
    title_routes,
)
from reelhaven.auth.network import IPAddress, read_default_gateways
from reelhaven.auth.throttle import LoginThrottle
from reelhaven.config import Settings, get_settings
from reelhaven.db import Database, Job
from reelhaven.devices import DeviceRegistry
from reelhaven.headers import SecurityHeadersMiddleware
from reelhaven.jobs.queue import JobQueue
from reelhaven.jobs.service import purge_expired
from reelhaven.live import ChangeFeed
from reelhaven.middleware import RequestLogMiddleware
from reelhaven.profiles import ensure_builtin_profiles
from reelhaven.resolver import LanguageResolver
from reelhaven.scanner import Scanner
from reelhaven.secretbox import SecretBox


def create_app(
    settings: Settings | None = None,
    gateways: frozenset[IPAddress] | None = None,
    detect_devices: bool = True,
) -> FastAPI:
    """Build the application.

    ``settings.web_dir`` is the built frontend (``frontend/dist``). When it is
    missing, only the API is served, which is normal while developing with
    Vite's dev server. ``gateways`` overrides Docker gateway detection (tests).
    """
    settings = settings or get_settings()
    db = Database(settings.config_dir / "reelhaven.db")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db.migrate()
        ensure_builtin_profiles(db)
        if detect_devices:
            app.state.devices.detect_in_background()
        app.state.queue.start()
        janitor = threading.Thread(
            target=_janitor, args=(db, app.state.stop), name="janitor", daemon=True
        )
        janitor.start()
        yield
        app.state.stop.set()
        app.state.queue.stop()
        db.close()

    app = FastAPI(
        title="ReelHaven",
        version=__version__,
        lifespan=lifespan,
        # OpenAPI docs are only served to authenticated users (SECURITY.md);
        # they are wired up behind auth in a later chunk.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.db = db
    app.state.throttle = LoginThrottle()
    app.state.gateways = read_default_gateways() if gateways is None else gateways
    app.state.gateway_seen_at = None
    app.state.devices = DeviceRegistry(settings.ffmpeg)
    app.state.queue = JobQueue(db, settings, app.state.devices)
    app.state.live = ChangeFeed()
    db.on_change(Job, app.state.live.changed)
    app.state.stop = threading.Event()
    app.state.secretbox = SecretBox(settings.config_dir)
    app.state.http_transport = None  # tests inject a fake transport
    app.state.scanner = Scanner(
        db,
        settings,
        resolve_languages=lambda library_id, force: LanguageResolver(
            db, app.state.secretbox, app.state.http_transport
        ).resolve_library(library_id, force),
    )
    # Last added runs first: log every request, including header-only responses.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLogMiddleware)

    app.include_router(auth_routes.router, prefix="/api/v1")
    app.include_router(security_routes.router, prefix="/api/v1")
    app.include_router(library_routes.router, prefix="/api/v1")
    app.include_router(file_routes.router, prefix="/api/v1")
    app.include_router(integration_routes.router, prefix="/api/v1")
    app.include_router(title_routes.router, prefix="/api/v1")
    app.include_router(job_routes.router, prefix="/api/v1")
    app.include_router(device_routes.router, prefix="/api/v1")
    app.include_router(profile_routes.router, prefix="/api/v1")
    app.include_router(test_run_routes.router, prefix="/api/v1")
    app.include_router(live_routes.router, prefix="/api/v1")

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        # Unauthenticated, no details (ARCHITECTURE.md §12).
        return {"status": "ok"}

    # Mounted last so API routes take precedence over static files.
    web_dir = settings.web_dir
    if web_dir is not None and (web_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app


def _janitor(db: Database, stop: threading.Event) -> None:
    """Hourly housekeeping: purge expired recycle bin entries."""
    while not stop.wait(timeout=60):
        try:
            purge_expired(db)
        except Exception:
            logging.getLogger(__name__).exception("recycle bin cleanup failed")
        stop.wait(timeout=3540)
