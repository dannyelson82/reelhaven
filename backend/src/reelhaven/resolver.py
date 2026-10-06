"""Original-language resolver (ARCHITECTURE.md §6.3, ADR-0007).

Order: Sonarr/Radarr (title folder matched by path) → TMDB (IDs in the folder
name, then an *exact* title + year match) → unknown. Manual overrides are
never replaced. Network failures keep the previous answer.
"""

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import PurePosixPath
from typing import Any

import httpx
from sqlalchemy import select

from reelhaven.db import Database, Integration, Library, MediaFile, Title
from reelhaven.db.types import utcnow
from reelhaven.integrations.clients import ArrClient, IntegrationError, TmdbClient
from reelhaven.integrations.pathmap import to_local
from reelhaven.integrations.service import client_for
from reelhaven.media.languages import normalise
from reelhaven.secretbox import SecretBox, SecretBoxError
from reelhaven.titles import comparable_title, parse_folder, title_folder

logger = logging.getLogger(__name__)

REFRESH_AFTER = timedelta(days=7)
RETRY_UNKNOWN_AFTER = timedelta(days=1)


@dataclass
class Answer:
    language: str | None
    source: str
    detail: str


@dataclass
class ResolveSummary:
    titles: int = 0
    resolved: int = 0
    unknown: int = 0
    errors: list[str] = field(default_factory=list)


def assign_titles(db: Database, library_id: int) -> None:
    """Create Title rows for every file's folder and link files to them."""
    with db.write() as session:
        library = session.get(Library, library_id)
        if library is None:
            return
        titles = {
            t.folder: t
            for t in session.scalars(select(Title).where(Title.library_id == library_id))
        }
        files = session.scalars(select(MediaFile).where(MediaFile.library_id == library_id))
        for media_file in files:
            folder = title_folder(media_file.relative_path, library.type)
            title = titles.get(folder)
            if title is None:
                info = parse_folder(folder)
                title = Title(library_id=library_id, folder=folder, name=info.name, year=info.year)
                session.add(title)
                session.flush()
                titles[folder] = title
            media_file.title_id = title.id
        # Titles without files any more are removed (overrides go with them).
        used = {
            f.title_id
            for f in session.scalars(select(MediaFile).where(MediaFile.library_id == library_id))
        }
        for title in titles.values():
            if title.id not in used:
                session.delete(title)


def _needs_resolving(title: Title, force: bool) -> bool:
    if title.language_source == "manual":
        return False
    if force or title.resolved_at is None:
        return True
    age = utcnow() - title.resolved_at
    if title.language_source == "unknown":
        return age > RETRY_UNKNOWN_AFTER
    return age > REFRESH_AFTER


class LanguageResolver:
    def __init__(
        self, db: Database, box: SecretBox, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._db = db
        self._box = box
        self._transport = transport

    def resolve_library(self, library_id: int, force: bool = False) -> ResolveSummary:
        assign_titles(self._db, library_id)
        summary = ResolveSummary()
        with self._db.read() as session:
            library = session.get(Library, library_id)
            if library is None:
                return summary
            titles = [
                t
                for t in session.scalars(select(Title).where(Title.library_id == library_id))
                if _needs_resolving(t, force)
            ]
            integrations = list(
                session.scalars(select(Integration).where(Integration.enabled.is_(True)))
            )
        summary.titles = len(titles)
        if not titles:
            return summary

        arr_kind = {"tv": "sonarr", "movies": "radarr"}.get(library.type)
        errors_before = len(summary.errors)
        arr_index = self._arr_index([i for i in integrations if i.kind == arr_kind], summary)
        # If Sonarr/Radarr couldn't be asked, "not found" means nothing: keep old answers.
        arr_failed = len(summary.errors) > errors_before
        tmdb = self._tmdb([i for i in integrations if i.kind == "tmdb"], summary)
        root = PurePosixPath(library.path)
        tmdb_kind = "tv" if library.type == "tv" else "movie"

        answers: dict[int, Answer] = {}
        for title in titles:
            folder = (root / title.folder).as_posix() if title.folder else None
            answer = arr_index.get(folder) if folder else None
            if answer is None and tmdb is not None:
                try:
                    answer = self._from_tmdb(tmdb, title, tmdb_kind)
                except IntegrationError as exc:
                    if exc.message not in summary.errors:
                        summary.errors.append(f"TMDB: {exc.message}")
                    continue  # keep the previous answer
            if answer is None and arr_failed:
                continue
            answers[title.id] = answer or Answer(None, "unknown", "No match found")
        if tmdb is not None:
            tmdb.close()

        now = utcnow()
        with self._db.write() as session:
            for title_id, answer in answers.items():
                row = session.get(Title, title_id)
                if row is None or row.language_source == "manual":
                    continue  # overridden while we were resolving
                row.original_language = answer.language
                row.language_source = answer.source
                row.source_detail = answer.detail[:512]
                row.resolved_at = now
                if answer.language:
                    summary.resolved += 1
                else:
                    summary.unknown += 1
        return summary

    def _arr_index(
        self, integrations: list[Integration], summary: ResolveSummary
    ) -> dict[str, Answer]:
        """Local folder path → answer, for every series/movie the services know."""
        index: dict[str, Answer] = {}
        for integration in integrations:
            try:
                with client_for(integration, self._box, self._transport) as client:
                    assert isinstance(client, ArrClient)  # noqa: S101
                    items = client.titles()
            except (IntegrationError, SecretBoxError) as exc:
                summary.errors.append(f"{integration.name}: {exc}")
                logger.warning("integration failed", extra={"integration": integration.name})
                continue
            for item in items:
                path = item.get("path")
                original = item.get("originalLanguage") or {}
                if not isinstance(path, str) or not isinstance(original, dict):
                    continue
                language = normalise(str(original.get("name") or ""))
                local = to_local(path, integration.path_mappings)
                index.setdefault(
                    local,
                    Answer(
                        language,
                        integration.kind if language else "unknown",
                        f"{integration.name}: {item.get('title', '?')}",
                    ),
                )
        return index

    def _tmdb(self, integrations: list[Integration], summary: ResolveSummary) -> TmdbClient | None:
        for integration in integrations:
            try:
                client = client_for(integration, self._box, self._transport)
            except SecretBoxError as exc:
                summary.errors.append(f"{integration.name}: {exc}")
                continue
            assert isinstance(client, TmdbClient)  # noqa: S101
            return client
        return None

    @staticmethod
    def _from_tmdb(client: TmdbClient, title: Title, kind: str) -> Answer | None:
        info = parse_folder(title.folder)
        candidates: list[tuple[str, dict[str, Any]]] = []
        if info.tmdb:
            candidates.append((kind, client.details(kind, info.tmdb)))  # type: ignore[arg-type]
        elif info.imdb or info.tvdb:
            source = "imdb_id" if info.imdb else "tvdb_id"
            found = client.find(info.imdb or info.tvdb or "", source)  # type: ignore[arg-type]
            candidates += [(r["media_type"], r) for r in found if r["media_type"] == kind]
        else:
            wanted = comparable_title(title.name)
            for result in client.search(kind, title.name, title.year):  # type: ignore[arg-type]
                names = [
                    result.get(k) for k in ("title", "name", "original_title", "original_name")
                ]
                date = str(result.get("release_date") or result.get("first_air_date") or "")
                year_ok = title.year is None or date[:4] == str(title.year)
                if year_ok and any(
                    isinstance(n, str) and comparable_title(n) == wanted for n in names
                ):
                    candidates.append((kind, result))
            if len(candidates) != 1:
                return None  # none, or ambiguous: don't guess
        for media_kind, result in candidates:
            language = normalise(str(result.get("original_language") or ""))
            if language:
                label = result.get("title") or result.get("name") or "?"
                return Answer(language, "tmdb", f"TMDB {media_kind} {result.get('id')}: {label}")
        return None
