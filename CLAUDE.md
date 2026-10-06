# Instructions for Claude Code

ReelHaven is an automatic, language-aware video library compression app for
Unraid. Before any work, read ARCHITECTURE.md and SECURITY.md; decisions are
recorded in docs/adr/.

## Rules
- Follow ARCHITECTURE.md and SECURITY.md. If something needs to change,
  propose a new ADR and wait for approval before implementing.
- Work in roadmap phase order (ARCHITECTURE.md §15). Plan each phase with the
  owner before writing its code.
- Workflow: one branch and pull request per chunk of a phase; CI must pass;
  Claude merges (squash) without waiting for review. Phase plans live in
  `docs/plans/`.
- Keep changes small, with clear conventional commit messages
  (`feat:`, `fix:`, `docs:`, `test:`, `chore:`). All commits signed.
- Never commit secrets, real media files, or personal infrastructure details
  (IPs, domains, container names). Setup-specific notes go in the gitignored
  LOCAL_NOTES.md.
- No sudo, no Docker socket. Images are built by GitHub Actions only.
- Sample media lives in /projects/reelhaven-testmedia, outside the repo.
  Tests generate their own fixtures with ffmpeg.
- Run ffmpeg/ffprobe only via argument lists, never through a shell.
- Planner and language logic must stay pure functions with thorough tests.
- The owner is comfortable following steps but is not a command-line expert:
  when they must do something themselves, give exact numbered steps and
  explain what each does. Discuss design before big decisions.

## Commands
Backend (run in `backend/`):
- Tests: `uv run pytest` (coverage: `uv run pytest --cov=reelhaven`)
- Lint, format, types: `uv run ruff check . && uv run ruff format --check . && uv run mypy`
- Auto-format: `uv run ruff format .`
- Run the server: `uv run python -m reelhaven` (port 7171, config in `./.dev-config`;
  add `REELHAVEN_WEB_DIR=../frontend/dist` to serve a built UI)
- New migration after model changes: `uv run python scripts/make_migration.py "what changed"`

Frontend (run in `frontend/`):
- Tests: `npm test`
- Lint, format, types: `npm run lint && npm run format:check && npm run typecheck`
- Auto-format: `npm run format`
- Build: `npm run build`
- Dev server with hot reload: `npm run dev` (port 5173, proxies `/api` to 7171)

Viewing the UI from code-server: build the frontend, run the backend with
`REELHAVEN_WEB_DIR=../frontend/dist`, then open `/proxy/7171/` on the
code-server address. The UI uses relative paths, so the proxy prefix works.

CI runs all of the above plus an image build and container smoke test
(`.github/workflows/`). `uv` warns that `VIRTUAL_ENV=/lsiopy` is ignored; that
comes from the code-server image and is harmless.
