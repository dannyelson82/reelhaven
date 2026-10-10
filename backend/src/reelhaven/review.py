"""The review page (ADR-0032): every file that needs the owner's decision, in one place.

``review_items`` is a pure function over facts gathered per file; ``gather`` reads
them from the database and the dry-run plans.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select

from reelhaven.db import Database, Job, Library, MediaFile
from reelhaven.dryrun import plan_library

ReviewKind = Literal["wrong_language", "skipped", "unreadable", "waiting", "failed", "no_gain"]
KINDS: tuple[ReviewKind, ...] = (
    "wrong_language",
    "failed",
    "unreadable",
    "skipped",
    "no_gain",
    "waiting",
)


@dataclass(frozen=True)
class FileFacts:
    file_id: int
    library_id: int
    library_name: str
    relative_path: str
    size: int
    mtime_ns: int
    flags: tuple[str, ...] = ()
    original_language: str | None = None
    audio_languages: tuple[str, ...] = ()
    unreadable: str | None = None  # the read error
    language_pending: bool = False
    failed_job: tuple[int, str] | None = None  # (job id, error) of the file's last job
    no_gain_video: bool = False
    no_gain_audio: bool = False
    ignored: dict[str, str] = field(default_factory=dict)  # kind -> "size:mtime"


@dataclass(frozen=True)
class ReviewItem:
    kind: ReviewKind
    file_id: int
    library_id: int
    library_name: str
    relative_path: str
    size: int
    detail: str
    ignored: bool
    job_id: int | None = None
    original_language: str | None = None
    audio_languages: tuple[str, ...] = ()


def file_state(size: int, mtime_ns: int) -> str:
    """What an ignore is tied to: the file as it was. A changed file shows up again."""
    return f"{size}:{mtime_ns}"


def _kinds(facts: FileFacts) -> list[tuple[ReviewKind, str, int | None]]:
    found: list[tuple[ReviewKind, str, int | None]] = []
    if facts.unreadable is not None:
        found.append(("unreadable", facts.unreadable or "The file couldn't be read.", None))
    if "wrong_language" in facts.flags or "no_wanted_audio" in facts.flags:
        # The page names the languages (audio_languages, original_language).
        found.append(("wrong_language", "None of the audio is in the library's languages.", None))
    if "dolby_vision" in facts.flags:
        found.append(("skipped", "Dolby Vision: not re-encoded, it would lose its layers.", None))
    elif "hdr10plus" in facts.flags:
        found.append(("skipped", "HDR10+: not re-encoded, it would lose its metadata.", None))
    if facts.failed_job is not None:
        job_id, error = facts.failed_job
        first = error.strip().splitlines()[0] if error.strip() else "The job failed."
        found.append(("failed", first, job_id))
    if facts.no_gain_video:
        found.append(("no_gain", "Re-encoding with this profile didn't save enough.", None))
    elif facts.no_gain_audio:
        found.append(("no_gain", "Converting the audio didn't make the file smaller.", None))
    if facts.language_pending:
        found.append(("waiting", "Waiting for the title's original language.", None))
    return found


def review_items(files: Iterable[FileFacts]) -> list[ReviewItem]:
    """Everything needing a decision, ignored items marked (they stay ignored until the
    file changes)."""
    items: list[ReviewItem] = []
    for facts in files:
        state = file_state(facts.size, facts.mtime_ns)
        for kind, detail, job_id in _kinds(facts):
            items.append(
                ReviewItem(
                    kind=kind,
                    file_id=facts.file_id,
                    library_id=facts.library_id,
                    library_name=facts.library_name,
                    relative_path=facts.relative_path,
                    size=facts.size,
                    detail=detail,
                    ignored=facts.ignored.get(kind) == state,
                    job_id=job_id,
                    original_language=facts.original_language,
                    audio_languages=tuple(sorted(set(facts.audio_languages))),
                )
            )
    return items


def _last_failed(db: Database, library_id: int) -> dict[int, tuple[int, str]]:
    """Files whose latest real job failed (tests and sweet-spot steps don't count)."""
    latest: dict[int, Job] = {}
    with db.read() as session:
        for job in session.scalars(
            select(Job)
            .where(
                Job.library_id == library_id,
                Job.media_file_id.is_not(None),
                Job.type.in_(("remux", "encode")),
            )
            .order_by(Job.id)
        ):
            assert job.media_file_id is not None  # noqa: S101
            latest[job.media_file_id] = job
    return {
        file_id: (job.id, job.error or "")
        for file_id, job in latest.items()
        if job.status == "failed"
    }


def gather(db: Database, library_ids: Iterable[int] | None = None) -> list[FileFacts]:
    with db.read() as session:
        libraries = {
            lib.id: lib.name
            for lib in session.scalars(select(Library))
            if library_ids is None or lib.id in set(library_ids)
        }
    facts: list[FileFacts] = []
    for library_id, library_name in libraries.items():
        plans = {p.file_id: p for p in plan_library(db, library_id)}
        failed = _last_failed(db, library_id)
        with db.read() as session:
            rows = session.execute(
                select(
                    MediaFile.id,
                    MediaFile.relative_path,
                    MediaFile.size,
                    MediaFile.mtime_ns,
                    MediaFile.status,
                    MediaFile.probe_error,
                    MediaFile.probe,
                    MediaFile.no_gain_profile,
                    MediaFile.no_gain_audio,
                    MediaFile.review_ignored,
                ).where(MediaFile.library_id == library_id)
            ).all()
        for row in rows:
            plan = plans.get(row.id)
            streams = (row.probe or {}).get("streams", []) if row.status == "ok" else []
            facts.append(
                FileFacts(
                    file_id=row.id,
                    library_id=library_id,
                    library_name=library_name,
                    relative_path=row.relative_path,
                    size=row.size,
                    mtime_ns=row.mtime_ns,
                    flags=tuple(plan.plan.flags) if plan and plan.plan else (),
                    original_language=plan.original_language if plan else None,
                    audio_languages=tuple(
                        s["language"]
                        for s in streams
                        if s.get("kind") == "audio" and s.get("language")
                    ),
                    unreadable=(row.probe_error or "") if row.status != "ok" else None,
                    language_pending=bool(plan and plan.language_pending),
                    failed_job=failed.get(row.id),
                    no_gain_video=row.no_gain_profile is not None,
                    no_gain_audio=row.no_gain_audio is not None,
                    ignored=dict(row.review_ignored or {}),
                )
            )
    return facts
