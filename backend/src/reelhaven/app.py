"""FastAPI application factory."""

from fastapi import FastAPI

from reelhaven import __version__


def create_app() -> FastAPI:
    app = FastAPI(
        title="ReelHaven",
        version=__version__,
        # OpenAPI docs are only served to authenticated users (SECURITY.md);
        # they are wired up behind auth in a later chunk.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        # Unauthenticated, no details (ARCHITECTURE.md §12).
        return {"status": "ok"}

    return app
