"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from reelhaven import __version__
from reelhaven.middleware import RequestLogMiddleware


def create_app(web_dir: Path | None = None) -> FastAPI:
    """Build the application.

    ``web_dir`` is the built frontend (``frontend/dist``). When it is missing,
    only the API is served, which is normal while developing with Vite's
    dev server.
    """
    app = FastAPI(
        title="ReelHaven",
        version=__version__,
        # OpenAPI docs are only served to authenticated users (SECURITY.md);
        # they are wired up behind auth in a later chunk.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(RequestLogMiddleware)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        # Unauthenticated, no details (ARCHITECTURE.md §12).
        return {"status": "ok"}

    # Mounted last so API routes take precedence over static files.
    if web_dir is not None and (web_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app
