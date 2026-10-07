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


def plan_library(db: Database, library_id: int) -> list[FilePlan]:
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
        result: list[FilePlan] = []
        for media_file, title in rows:
            original = title.original_language if title else None
            file_plan = None
            if media_file.status == "ok" and media_file.probe is not None:
                info = MediaInfo.model_validate(media_file.probe)
                file_plan = plan_file(info, original, policy, profile)
            result.append(
                FilePlan(
                    media_file.id, media_file.relative_path, media_file.size, original, file_plan
                )
            )
    return result


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


def summarise(plans: list[FilePlan]) -> DryRunSummary:
    flags: Counter[str] = Counter()
    encode = remux = unchanged = unreadable = unknown = saved = savings_unknown = 0
    for item in plans:
        if item.original_language is None:
            unknown += 1
        if item.plan is None:
            unreadable += 1
            continue
        flags.update(item.plan.flags)
        video = item.plan.video
        if item.plan.action == "encode" and video is not None:
            encode += 1
            if video.bytes_after_estimate is None or video.bytes_before is None:
                savings_unknown += 1
            else:
                saved += video.bytes_before - video.bytes_after_estimate
        elif item.plan.action == "remux":
            remux += 1
            if item.plan.removed_bytes is None:
                savings_unknown += 1
            else:
                saved += item.plan.removed_bytes
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
    )
