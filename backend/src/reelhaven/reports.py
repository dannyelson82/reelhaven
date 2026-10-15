"""Plain-text reports to send when asking for help (ADR-0033).

The formatting functions are pure; ``failed_jobs`` reads the database. Reports are
redacted with the logging filter, so API keys and passwords never appear in them.
"""

import shlex
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select

from reelhaven.db import Database, Job, Library, MediaFile, Title
from reelhaven.logsetup import redact
from reelhaven.media.info import MediaInfo, Stream
from reelhaven.review import ReviewItem

RULE = "=" * 78


@dataclass(frozen=True)
class FailedJob:
    id: int
    type: str
    status: str
    cleared: bool
    library: str | None
    path: str
    requested_by: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    device: str | None
    decoder: str | None
    profile: dict[str, Any] | None
    plan: dict[str, Any]
    probe: dict[str, Any]
    command: list[str] | None
    error: str | None


def header(title: str, version: str, devices: Iterable[str], now: datetime) -> list[str]:
    return [
        f"ReelHaven {title}",
        f"Version: {version}",
        f"Created: {now.isoformat(timespec='seconds')}",
        "Devices: " + (", ".join(devices) or "none detected"),
        "",
    ]


def _size(n: int | None) -> str:
    if n is None:
        return "?"
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1000
    return f"{n} B"


def _hdr(stream: Stream) -> str:
    hdr: str = stream.hdr or "?"
    if stream.hdr == "dolby_vision":
        if stream.dv_profile is not None:
            compat = "" if stream.dv_compat_id is None else f".{stream.dv_compat_id}"
            hdr += f" profile {stream.dv_profile}{compat}"
        else:
            hdr += " (profile unknown: read before 0.9.2)"
    colours = [c for c in (stream.color_transfer, stream.color_primaries) if c]
    return hdr + (f" [{' / '.join(colours)}]" if colours else "")


def describe_stream(stream: Stream) -> str:
    parts = [f"#{stream.index} {stream.kind}", stream.codec or "?"]
    if stream.profile:
        parts.append(f"({stream.profile})")
    if stream.kind == "video":
        parts.append(f"{stream.width or '?'}x{stream.height or '?'}")
        if stream.bit_depth:
            parts.append(f"{stream.bit_depth}-bit")
        if stream.pix_fmt:
            parts.append(stream.pix_fmt)
        if stream.frame_rate:
            parts.append(f"{stream.frame_rate:.3f} fps")
        parts.append(_hdr(stream))
    else:
        parts.append(stream.language or f"untagged ({stream.raw_language or 'none'})")
    if stream.kind == "audio":
        parts.append(f"{stream.channels or '?'} ch")
        if stream.channel_layout:
            parts.append(stream.channel_layout)
    if stream.kind == "subtitle" and stream.image_based:
        parts.append("image")
    if stream.bit_rate:
        parts.append(f"{stream.bit_rate // 1000} kbit/s")
    flags = [
        name
        for name, on in (
            ("default", stream.default),
            ("forced", stream.forced),
            ("SDH", stream.hearing_impaired),
            ("commentary", stream.commentary),
        )
        if on
    ]
    if flags:
        parts.append("[" + ", ".join(flags) + "]")
    if stream.title:
        parts.append(f'"{stream.title}"')
    return " ".join(parts)


def describe_media(probe: dict[str, Any]) -> list[str]:
    """What the file contained, one line per track."""
    try:
        info = MediaInfo.model_validate(probe)
    except ValidationError:
        return ["  (no file details recorded)"]
    duration = f"{info.duration_s / 60:.1f} min" if info.duration_s else "?"
    lines = [f"  {info.container}, {duration}, {_size(info.size_bytes)}"]
    lines += [f"  {describe_stream(s)}" for s in info.streams]
    return lines


def _time(value: datetime | None) -> str:
    return value.isoformat(timespec="seconds") if value else "-"


def describe_failure(job: FailedJob) -> list[str]:
    status = job.status + (" (cleared from the Failed tab by a retry)" if job.cleared else "")
    lines = [
        RULE,
        f"Job #{job.id} - {job.type} - {status}",
        f"File: {job.path}",
        f"Library: {job.library or '-'}  Requested by: {job.requested_by}",
        f"Created {_time(job.created_at)}  Started {_time(job.started_at)}  "
        f"Finished {_time(job.finished_at)}",
    ]
    if job.device:
        lines.append(f"Device: {job.device}  Decoding: {job.decoder or '?'}")
    if job.profile:
        profile = ", ".join(f"{k}={v}" for k, v in sorted(job.profile.items()))
        lines.append(f"Profile: {profile}")
    lines += ["", "Source:", *describe_media(job.probe), "", "Plan:"]
    summary = str(job.plan.get("summary") or "").strip()
    if summary:
        lines.append(f"  {summary}")
    lines += [f"  - {d}" for d in job.plan.get("details") or []]
    lines += ["", "ffmpeg command:"]
    lines.append(f"  {shlex.join(job.command)}" if job.command else "  (not recorded)")
    lines += ["", "Error:"]
    lines += [f"  {line}" for line in (job.error or "(none recorded)").splitlines()]
    lines.append("")
    return lines


def failure_report(
    jobs: list[FailedJob], version: str, devices: Iterable[str], now: datetime
) -> str:
    lines = header("failure report", version, devices, now)
    cleared = sum(1 for j in jobs if j.cleared)
    lines.append(
        f"{len(jobs)} failed job(s), newest first"
        + (f" ({cleared} cleared by a retry)" if cleared else "")
    )
    lines.append("")
    for job in jobs:
        lines += describe_failure(job)
    return redact("\n".join(lines) + "\n")


def failed_jobs(db: Database) -> list[FailedJob]:
    """Every failed job, newest first, including the ones a retry cleared."""
    with db.read() as session:
        libraries = {lib.id: lib.name for lib in session.scalars(select(Library))}
        rows = session.scalars(select(Job).where(Job.status == "failed").order_by(Job.id.desc()))
        return [
            FailedJob(
                id=job.id,
                type=job.type,
                status=job.status,
                cleared=job.cleared_at is not None,
                library=libraries.get(job.library_id) if job.library_id else None,
                path=job.source_path,
                requested_by=job.requested_by,
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
                device=job.device,
                decoder=job.decoder,
                profile=job.profile,
                plan=job.plan or {},
                probe=job.probe or {},
                command=job.command,
                error=job.error,
            )
            for job in rows
        ]


# --- review report ---------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewFacts:
    item: ReviewItem
    probe: dict[str, Any] | None
    title: str | None
    language_source: str | None  # where the original language came from
    job_error: str | None  # the last job's full error, for failed items


@dataclass(frozen=True)
class ResolvedEntry:
    library: str
    path: str
    kind: str
    detail: str
    first_seen_at: datetime
    resolved_at: datetime


def describe_review_item(facts: ReviewFacts) -> list[str]:
    item = facts.item
    lines = [
        RULE,
        f"{item.kind}{' (ignored)' if item.ignored else ''}: {item.library_name} / "
        f"{item.relative_path}",
        f"Why: {item.detail}",
        f"Size: {_size(item.size)}",
    ]
    if facts.title:
        lines.append(f"Title: {facts.title}")
    language = item.original_language or "not known yet"
    source = f" (from {facts.language_source})" if facts.language_source else ""
    lines.append(f"Original language: {language}{source}")
    lines.append(f"Audio languages: {', '.join(item.audio_languages) or 'none tagged'}")
    lines += ["", "File:", *describe_media(facts.probe or {})]
    if item.job_id is not None:
        lines += ["", f"Last job #{item.job_id} error:"]
        lines += [f"  {line}" for line in (facts.job_error or "(none recorded)").splitlines()]
    lines.append("")
    return lines


def review_report(
    current: list[ReviewFacts],
    resolved: list[ResolvedEntry],
    version: str,
    devices: Iterable[str],
    now: datetime,
) -> str:
    lines = header("review report", version, devices, now)
    by_kind: dict[str, int] = {}
    for facts in current:
        by_kind[facts.item.kind] = by_kind.get(facts.item.kind, 0) + 1
    summary = ", ".join(f"{kind} {count}" for kind, count in sorted(by_kind.items()))
    lines.append(f"{len(current)} file(s) on the Review page" + (f": {summary}" if summary else ""))
    lines.append(f"{len(resolved)} resolved in the last 90 days (listed at the end)")
    lines.append("")
    for facts in current:
        lines += describe_review_item(facts)
    if resolved:
        lines += [RULE, "Resolved in the last 90 days, newest first:", ""]
        lines += [
            f"  {_time(r.resolved_at)}  {r.kind}: {r.library} / {r.path}  ({r.detail}; "
            f"listed since {_time(r.first_seen_at)})"
            for r in resolved
        ]
    return redact("\n".join(lines) + "\n")


def review_facts(db: Database, items: list[ReviewItem]) -> list[ReviewFacts]:
    """What the database knows about each review item's file."""
    file_ids = {i.file_id for i in items}
    job_ids = {i.job_id for i in items if i.job_id is not None}
    with db.read() as session:
        files = {
            f.id: f for f in session.scalars(select(MediaFile).where(MediaFile.id.in_(file_ids)))
        }
        titles = {
            t.id: t
            for t in session.scalars(
                select(Title).where(Title.id.in_({f.title_id for f in files.values()}))
            )
        }
        errors = {j.id: j.error for j in session.scalars(select(Job).where(Job.id.in_(job_ids)))}
        out = []
        for item in items:
            media_file = files.get(item.file_id)
            title = titles.get(media_file.title_id) if media_file and media_file.title_id else None
            out.append(
                ReviewFacts(
                    item=item,
                    probe=media_file.probe if media_file else None,
                    title=f"{title.name} ({title.year})"
                    if title and title.year
                    else (title.name if title else None),
                    language_source=(
                        f"{title.language_source}"
                        + (f": {title.source_detail}" if title.source_detail else "")
                        if title
                        else None
                    ),
                    job_error=errors.get(item.job_id) if item.job_id is not None else None,
                )
            )
        return out
