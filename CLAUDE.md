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

## Commands (fill in during phase 0.1)
- Backend tests: `TBD`
- Frontend dev server: `TBD`
- Lint/format: `TBD`
