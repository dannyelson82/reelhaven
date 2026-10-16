"""Colour check (ADR-0036): find Dolby Vision profile 5 pictures that lost their Dolby
Vision record and now play green and purple everywhere.

``is_candidate``, ``frame_sample``, ``verdict`` and ``result`` are pure; ``measure``
runs ffmpeg.
"""

import logging
import subprocess
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import String, cast, func, or_, select

from reelhaven.cpu_limit import preexec
from reelhaven.db import Database, MediaFile
from reelhaven.media.info import MediaInfo
from reelhaven.media.probe import ffmpeg_input

logger = logging.getLogger(__name__)

Verdict = Literal["ok", "wrong_colours"]

POINTS = tuple(i / 13 for i in range(1, 13))  # 12 frames spread through the file
WIDTH = 160  # frames are scaled down to this before counting pixels
LIT = 40  # pixels darker than this (0-255) don't count: too dark to have a colour
MARGIN = 12  # a channel must beat the other two by this much
GREEN_MEAN = 0.20  # mean share of green pixels across the frames ...
GREEN_FRAME = 0.25  # ... and frames at least this green ...
GREEN_FRAMES_NEEDED = 4  # ... at least this many of them
_UNTAGGED = {None, "", "unknown", "unspecified", "reserved"}


def is_candidate(info: MediaInfo) -> bool:
    """10-bit SDR with no Dolby Vision record and no colour tags: the fingerprint of a
    Dolby Vision profile 5 picture re-encoded as ordinary video."""
    video = info.video
    if video is None or (video.bit_depth or 0) < 10 or video.hdr not in (None, "sdr"):
        return False
    if video.dv_profile is not None:
        return False
    return video.color_transfer in _UNTAGGED and video.color_primaries in _UNTAGGED


def state_of(size: int, mtime_ns: int) -> str:
    """What a result is tied to: the file as it was. A changed file is checked again."""
    return f"{size}:{mtime_ns}"


@dataclass(frozen=True)
class Sample:
    green: float  # share of lit pixels where green clearly beats red and blue
    magenta: float  # share where red and blue both clearly beat green


def frame_sample(rgb: bytes) -> Sample | None:
    """Count green and magenta pixels in a raw RGB24 frame; None when it's too dark."""
    lit = green = magenta = 0
    for i in range(0, len(rgb) - 2, 3):
        r, g, b = rgb[i], rgb[i + 1], rgb[i + 2]
        if max(r, g, b) <= LIT:
            continue
        lit += 1
        if g > r + MARGIN and g > b + MARGIN:
            green += 1
        elif r > g + MARGIN and b > g + MARGIN:
            magenta += 1
    return Sample(green / lit, magenta / lit) if lit else None


def verdict(samples: Sequence[Sample]) -> Verdict:
    """A green cast through most of the file: the IPT picture of Dolby Vision profile 5
    shown as ordinary video. One green scene isn't enough."""
    if len(samples) < GREEN_FRAMES_NEEDED:
        return "ok"
    mean = sum(s.green for s in samples) / len(samples)
    green_frames = sum(1 for s in samples if s.green >= GREEN_FRAME)
    if mean >= GREEN_MEAN and green_frames >= GREEN_FRAMES_NEEDED:
        return "wrong_colours"
    return "ok"


def result(samples: Sequence[Sample], state: str) -> dict[str, Any]:
    """What is stored on the file (``media_files.colour_check``)."""
    n = len(samples) or 1
    return {
        "state": state,
        "verdict": verdict(samples),
        "frames": len(samples),
        "green": round(sum(s.green for s in samples) / n, 3),
        "magenta": round(sum(s.magenta for s in samples) / n, 3),
        "green_frames": sum(1 for s in samples if s.green >= GREEN_FRAME),
    }


def describe(check: dict[str, Any]) -> str:
    green = round(100 * float(check.get("green") or 0))
    return (
        "Green and purple picture: probably a Dolby Vision profile 5 file that lost its "
        f"Dolby Vision information ({green} % of the picture is green, in "
        f"{check.get('green_frames')} of {check.get('frames')} frames checked)."
    )


def measure(ffmpeg: str, path: Path, duration_s: float, timeout_s: float = 120) -> list[Sample]:
    """One keyframe near each of ``POINTS``, scaled down and counted. Frames that can't be
    read, or are too dark to judge, are left out."""
    samples: list[Sample] = []
    for point in POINTS:
        args = [
            ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
            "-skip_frame", "nokey", "-ss", f"{duration_s * point:.3f}",
            "-i", ffmpeg_input(path), "-map", "0:v:0", "-frames:v", "1",
            "-vf", f"scale={WIDTH}:-2:flags=area,format=rgb24", "-f", "rawvideo", "-",
        ]  # fmt: skip
        try:
            run = subprocess.run(  # noqa: S603 - argument list, no shell
                args, capture_output=True, timeout=timeout_s, check=False, preexec_fn=preexec()
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        sample = frame_sample(run.stdout) if run.returncode == 0 else None
        if sample is not None:
            samples.append(sample)
    return samples


# --- the background checker -------------------------------------------------------------

BATCH = 200
IDLE_S = 600.0  # after a full pass with nothing to check, look again this much later


def next_unchecked(db: Database, after_id: int) -> list[tuple[int, str, int, int, dict[str, Any]]]:
    """Files after ``after_id`` with no result for their current size and time."""
    state = cast(MediaFile.size, String) + ":" + cast(MediaFile.mtime_ns, String)
    with db.read() as session:
        rows = session.execute(
            select(
                MediaFile.id, MediaFile.path, MediaFile.size, MediaFile.mtime_ns, MediaFile.probe
            )
            .where(
                MediaFile.id > after_id,
                MediaFile.status == "ok",
                MediaFile.probe.is_not(None),
                or_(
                    MediaFile.colour_check.is_(None),
                    func.json_extract(MediaFile.colour_check, "$.state") != state,
                ),
            )
            .order_by(MediaFile.id)
            .limit(BATCH)
        ).all()
    return [(r[0], r[1], r[2], r[3], r[4] or {}) for r in rows]


class ColourChecker:
    """Checks candidates one at a time, at low priority, in the background (ADR-0036).
    Files that aren't candidates get a cheap "not checked" result, so each file is only
    looked at again when it changes."""

    def __init__(self, db: Database, ffmpeg: str, paused: Callable[[], bool]) -> None:
        self._db = db
        self._ffmpeg = ffmpeg
        self._paused = paused
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="colour-check", daemon=True)
        self._thread.start()

    def poke(self) -> None:
        """Look for new files soon (e.g. a scan finished)."""
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                checked = self.run_pass()
            except Exception:
                logger.exception("colour check failed")
                checked = 0
            self._wake.wait(IDLE_S if checked == 0 else 1.0)
            self._wake.clear()

    def run_pass(self) -> int:
        """Go through every file once; returns how many were measured."""
        measured = 0
        after = 0
        while not self._stop.is_set():
            rows = next_unchecked(self._db, after)
            if not rows:
                break
            for file_id, path, size, mtime_ns, probe in rows:
                if self._stop.is_set():
                    break
                while self._paused() and not self._stop.is_set():
                    self._stop.wait(30)
                after = file_id
                state = state_of(size, mtime_ns)
                info = MediaInfo.model_validate(probe)
                if is_candidate(info):
                    samples = measure(self._ffmpeg, Path(path), info.duration_s or 0.0)
                    check = result(samples, state)
                    measured += 1
                    if check["verdict"] == "wrong_colours":
                        logger.warning("wrong colours", extra={"path": path, **check})
                else:
                    check = {"state": state, "verdict": "not_checked"}
                self._save(file_id, check)
        return measured

    def _save(self, file_id: int, check: dict[str, Any]) -> None:
        with self._db.write() as session:
            row = session.get(MediaFile, file_id)
            if row is not None:
                row.colour_check = check
