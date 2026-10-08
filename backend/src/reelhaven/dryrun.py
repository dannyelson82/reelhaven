"""Dry run (ARCHITECTURE.md §9): plan every file of a library. Read-only."""

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select

from reelhaven.db import Database, Library, MediaFile, Profile, Title
from reelhaven.media.info import MediaInfo
from reelhaven.planner import Plan, plan_file
from reelhaven.policy import LanguagePolicy
from reelhaven.profiles import ProfileSettings


@dataclass
class FilePlan:
    file_id: int
    relative_path: str
    size: int
    original_language: str | None
    plan: Plan | None  # None: the file couldn't be read
    # The title's original language hasn't been looked up yet (new files while a
    # scan runs, or Sonarr/Radarr/TMDB couldn't be reached). Planned without it, a
    # file could lose its original-language audio, so it is never queued until then.
    language_pending: bool = False


@dataclass
class _Source:
    file_id: int
    relative_path: str
    size: int
    original_language: str | None
    info: MediaInfo | None
    no_gain_profile: str | None
    language_pending: bool


def _language_pending(title: Title | None) -> bool:
    return title is None or (title.resolved_at is None and title.language_source != "manual")


def _load(
    db: Database, library_id: int
) -> tuple[LanguagePolicy, ProfileSettings | None, list[_Source]]:
    with db.read() as session:
        library = session.get(Library, library_id)
        if library is None:
            raise LookupError("library_not_found")
        policy = LanguagePolicy.model_validate(library.language_policy or {})
        profile_row = session.get(Profile, library.profile_id) if library.profile_id else None
        profile = ProfileSettings.model_validate(profile_row.settings) if profile_row else None
        rows = session.execute(
            select(MediaFile, Title)
            .outerjoin(Title, Title.id == MediaFile.title_id)
            .where(MediaFile.library_id == library_id)
            .order_by(MediaFile.relative_path)
        ).all()
        sources = [
            _Source(
                media_file.id,
                media_file.relative_path,
                media_file.size,
                title.original_language if title else None,
                MediaInfo.model_validate(media_file.probe)
                if media_file.status == "ok" and media_file.probe is not None
                else None,
                media_file.no_gain_profile,
                _language_pending(title),
            )
            for media_file, title in rows
        ]
    return policy, profile, sources


def _plan(
    sources: list[_Source], policy: LanguagePolicy, profile: ProfileSettings | None
) -> list[FilePlan]:
    return [
        FilePlan(
            s.file_id,
            s.relative_path,
            s.size,
            s.original_language,
            None
            if s.info is None
            else plan_file(s.info, s.original_language, policy, profile, s.no_gain_profile),
            s.language_pending,
        )
        for s in sources
    ]


def plan_library(db: Database, library_id: int) -> list[FilePlan]:
    policy, profile, sources = _load(db, library_id)
    return _plan(sources, policy, profile)


def estimate(
    db: Database, library_id: int, candidates: dict[str, ProfileSettings | None]
) -> dict[str, "DryRunSummary"]:
    """The dry run's totals as if the library used each candidate profile. Read-only:
    the files are loaded once and nothing is saved (used by the setup wizard)."""
    policy, _current, sources = _load(db, library_id)
    return {
        name: summarise(_plan(sources, policy, profile)) for name, profile in candidates.items()
    }


@dataclass
class DryRunSummary:
    files: int
    encode: int
    remux: int
    unchanged: int
    unreadable: int
    flags: dict[str, int]
    unknown_original: int
    saved_bytes: int
    savings_unknown: int
    waiting_for_language: int = 0  # changes held back until the language is known


def summarise(plans: list[FilePlan]) -> DryRunSummary:
    flags: Counter[str] = Counter()
    encode = remux = unchanged = unreadable = unknown = saved = savings_unknown = 0
    waiting = 0
    for item in plans:
        if item.original_language is None and not item.language_pending:
            unknown += 1
        if item.plan is None:
            unreadable += 1
            continue
        flags.update(item.plan.flags)
        if item.language_pending and item.plan.action in ("encode", "remux"):
            waiting += 1
        video = item.plan.video
        if item.plan.action == "encode" and video is not None:
            encode += 1
            if video.bytes_after_estimate is None or video.bytes_before is None:
                savings_unknown += 1
            else:
                saved += video.bytes_before - video.bytes_after_estimate
        elif item.plan.action == "remux":
            remux += 1
            if item.plan.remux_saved_bytes is None:
                savings_unknown += 1
            else:
                saved += item.plan.remux_saved_bytes
        else:
            unchanged += 1
    return DryRunSummary(
        files=len(plans),
        encode=encode,
        remux=remux,
        unchanged=unchanged,
        unreadable=unreadable,
        flags=dict(flags),
        unknown_original=unknown,
        saved_bytes=saved,
        savings_unknown=savings_unknown,
        waiting_for_language=waiting,
    )
