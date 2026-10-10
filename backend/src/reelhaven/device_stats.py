"""Per-device performance and job throughput (ADR-0032). Pure functions over finished jobs."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class JobRow:
    """One finished job, as far as the stats care."""

    finished: datetime  # local time
    type: str  # "encode", "remux", …
    status: str  # "done", "failed", "cancelled"
    device: str | None
    decoder: str | None  # "gpu" | "cpu" | None
    outcome: str | None  # JobResult: "replaced" | "no_gain" | None
    saved: int  # bytes; 0 unless replaced
    video_seconds: float | None  # length of the video encoded
    work_seconds: float | None  # how long the job took
    fps: float | None


@dataclass(frozen=True)
class DeviceStats:
    device: str
    files: int  # encodes finished (replaced or no gain)
    failed: int
    saved: int
    video_hours: float
    work_hours: float
    # Hours of video per hour of work: 4.0 means four times real time.
    speed: float | None
    # Average frames per second, weighted by video length.
    fps: float | None
    gpu_decoded: float | None  # share of encodes whose source the GPU decoded, 0-1


@dataclass(frozen=True)
class Day:
    day: date
    encoded: int
    remuxed: int
    failed: int
    saved: int


def device_stats(rows: list[JobRow], since: datetime | None = None) -> list[DeviceStats]:
    """Encodes per device since ``since`` (all time if None), busiest first."""
    groups: dict[str, list[JobRow]] = defaultdict(list)
    for row in rows:
        if row.type == "encode" and row.device and (since is None or row.finished >= since):
            groups[row.device].append(row)
    out: list[DeviceStats] = []
    for device, items in groups.items():
        done = [r for r in items if r.status == "done" and r.outcome is not None]
        video = sum(r.video_seconds or 0 for r in done)
        work = sum(r.work_seconds or 0 for r in done)
        timed = [r for r in done if r.fps and r.video_seconds]
        weight = sum(r.video_seconds or 0 for r in timed)
        decoded = [r for r in done if r.decoder in ("gpu", "cpu")]
        out.append(
            DeviceStats(
                device=device,
                files=len(done),
                failed=sum(1 for r in items if r.status == "failed"),
                saved=sum(r.saved for r in done),
                video_hours=round(video / 3600, 2),
                work_hours=round(work / 3600, 2),
                speed=round(video / work, 2) if work > 0 else None,
                fps=round(sum((r.fps or 0) * (r.video_seconds or 0) for r in timed) / weight, 1)
                if weight > 0
                else None,
                gpu_decoded=round(sum(1 for r in decoded if r.decoder == "gpu") / len(decoded), 3)
                if decoded
                else None,
            )
        )
    return sorted(out, key=lambda d: (-d.files, d.device))


def daily(rows: list[JobRow], today: date, days: int = 30) -> list[Day]:
    """Jobs finished per day for the last ``days`` days, oldest first, empty days included."""
    first = today - timedelta(days=days - 1)
    counts: dict[date, list[int]] = {first + timedelta(days=i): [0, 0, 0, 0] for i in range(days)}
    for row in rows:
        bucket = counts.get(row.finished.date())
        if bucket is None:
            continue
        if row.status == "failed" and row.type in ("encode", "remux"):
            bucket[2] += 1
        elif row.status == "done" and row.type == "encode" and row.outcome is not None:
            bucket[0] += 1
            bucket[3] += row.saved
        elif row.status == "done" and row.type == "remux" and row.outcome is not None:
            bucket[1] += 1
            bucket[3] += row.saved
    return [Day(day, *values) for day, values in counts.items()]
