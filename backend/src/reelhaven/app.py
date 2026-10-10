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
    automation_routes,
    device_routes,
    file_routes,
    film_routes,
    integration_routes,
    job_routes,
    library_routes,
    live_routes,
    onboarding_routes,
    profile_routes,
    recycle_settings_routes,
    review_routes,
    security_routes,
    stats_routes,
    test_run_routes,
    title_routes,
    tune_routes,
    upcoming_routes,
    webhook_routes,
)
from reelhaven.auth.network import IPAddress, read_default_gateways
from reelhaven.auth.throttle import LoginThrottle
from reelhaven.automation import Automation
from reelhaven.config import Settings, get_settings
from reelhaven.db import Database, Job
from reelhaven.devices import DeviceRegistry
from reelhaven.films import FilmLibrary
from reelhaven.headers import SecurityHeadersMiddleware
from reelhaven.integrations.research import ask_for_new_release
from reelhaven.jobs.queue import JobQueue
from reelhaven.jobs.service import purge_expired
from reelhaven.live import ChangeFeed
from reelhaven.middleware import RequestLogMiddleware
from reelhaven.notify import Notifier
from reelhaven.profiles import ensure_builtin_profiles
from reelhaven.resolver import LanguageResolver
from reelhaven.scanner import Scanner
from reelhaven.secretbox import SecretBox
from reelhaven.watcher import FolderWatcher


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
        # A finished job lets Automatic queue the next one straight away.
        app.state.queue.on_job_finished = app.state.automation.poke
        app.state.queue.start()
        app.state.automation.start()
        app.state.watcher.start()
        app.state.notifier.start()
        janitor = threading.Thread(
            target=_janitor, args=(db, app.state.stop), name="janitor", daemon=True
        )
        janitor.start()
        yield
        app.state.stop.set()
        app.state.automation.stop()
        app.state.watcher.stop()
        app.state.notifier.stop()
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
    app.state.films = FilmLibrary(settings.config_dir / "films")
    app.state.queue = JobQueue(db, settings, app.state.devices)
    app.state.live = ChangeFeed()
    # Lambdas: tests swap the scanner and queue after create_app.
    app.state.automation = Automation(
        db,
        start_scan=lambda library_id: app.state.scanner.start(library_id),
        notify_queue=lambda: app.state.queue.notify(),
        encode_slots=lambda: app.state.queue.encode_slots(),
        remux_slots=lambda: app.state.queue.remux_slots(),
    )
    app.state.watcher = FolderWatcher(
        db,
        start_scan=lambda library_id, folders: app.state.scanner.start(library_id, folders=folders),
    )
    app.state.notifier = Notifier(
        db,
        box=lambda: app.state.secretbox,
        transport=lambda: app.state.http_transport,
    )
    db.on_change(Job, app.state.live.changed)
    app.state.stop = threading.Event()
    app.state.secretbox = SecretBox(settings.config_dir)
    app.state.http_transport = None  # tests inject a fake transport
    app.state.queue.research = lambda path: ask_for_new_release(
        db, app.state.secretbox, app.state.http_transport, path
    )
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
    app.include_router(tune_routes.router, prefix="/api/v1")
    app.include_router(film_routes.router, prefix="/api/v1")
    app.include_router(review_routes.router, prefix="/api/v1")
    app.include_router(upcoming_routes.router, prefix="/api/v1")
    app.include_router(live_routes.router, prefix="/api/v1")
    app.include_router(automation_routes.router, prefix="/api/v1")
    app.include_router(recycle_settings_routes.router, prefix="/api/v1")
    app.include_router(webhook_routes.router, prefix="/api/v1")
    app.include_router(onboarding_routes.router, prefix="/api/v1")
    app.include_router(stats_routes.router, prefix="/api/v1")

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
