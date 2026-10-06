# 0002: Python and FastAPI for the backend

- Status: accepted
- Date: 2026-10-06

## Context
The heavy work is done by ffmpeg. The application orchestrates it: probing,
planning, running and monitoring processes, and calling the Sonarr, Radarr,
Plex, Jellyfin and TMDB APIs. Go was considered for a leaner image.

## Decision
Python 3.12+ with FastAPI and Uvicorn. Tooling: uv (environments and
dependencies), ruff (lint + format), mypy (types), pytest.

## Consequences
- Fast feature development and mature libraries for every integration.
- Typed Pydantic models double as API validation and documentation.
- Slightly larger image than Go; irrelevant next to ffmpeg's cost.
