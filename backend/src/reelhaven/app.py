"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from reelhaven import __version__
from reelhaven.api import auth_routes, file_routes, library_routes, security_routes
from reelhaven.auth.network import IPAddress, read_default_gateways
from reelhaven.auth.throttle import LoginThrottle
from reelhaven.config import Settings, get_settings
from reelhaven.db import Database
from reelhaven.headers import SecurityHeadersMiddleware
from reelhaven.middleware import RequestLogMiddleware
from reelhaven.scanner import Scanner


def create_app(
    settings: Settings | None = None, gateways: frozenset[IPAddress] | None = None
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
        yield
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
    app.state.scanner = Scanner(db, settings)
    # Last added runs first: log every request, including header-only responses.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLogMiddleware)

    app.include_router(auth_routes.router, prefix="/api/v1")
    app.include_router(security_routes.router, prefix="/api/v1")
    app.include_router(library_routes.router, prefix="/api/v1")
    app.include_router(file_routes.router, prefix="/api/v1")

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        # Unauthenticated, no details (ARCHITECTURE.md §12).
        return {"status": "ok"}

    # Mounted last so API routes take precedence over static files.
    web_dir = settings.web_dir
    if web_dir is not None and (web_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app
