# 0005: React and TypeScript frontend served by the backend

- Status: accepted
- Date: 2026-10-06

## Context
The UI needs live job progress, a stats dashboard, editors and a setup wizard.

## Decision
React + TypeScript built with Vite, compiled to static files served by
FastAPI from the same container. Live updates over a WebSocket. A standard
charting library for stats.

## Consequences
- Widely known stack with many examples.
- Node.js is needed to build, not to run; the final image contains only the
  built static files.
