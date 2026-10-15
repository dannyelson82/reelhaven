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

from reelhaven.db import Database, Job, Library
from reelhaven.logsetup import redact
from reelhaven.media.info import MediaInfo, Stream

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
