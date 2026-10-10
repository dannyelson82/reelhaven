"""Run ffprobe safely (SECURITY.md "Process execution").

Always an argument list (never a shell), always an absolute path behind the
``file:`` protocol prefix (so names can't be read as options or URLs), and
always with a timeout.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from reelhaven.cpu_limit import preexec
from reelhaven.media.info import MediaInfo, parse

logger = logging.getLogger(__name__)

_MAX_ERROR_CHARS = 500


class ProbeError(Exception):
    """ffprobe failed, timed out, or returned something unreadable."""


def ffmpeg_input(path: Path) -> str:
    """The safe way to name a local file on an ffmpeg/ffprobe command line."""
    if not path.is_absolute():
        raise ValueError("media paths must be absolute")
    return f"file:{path}"


def _run(args: list[str], timeout: float) -> dict[str, Any]:
    try:
        completed = subprocess.run(  # noqa: S603 - argument list, no shell
            args, capture_output=True, timeout=timeout, check=False, preexec_fn=preexec()
        )
    except subprocess.TimeoutExpired as exc:
        raise ProbeError(f"ffprobe timed out after {timeout:.0f}s") from exc
    except OSError as exc:
        raise ProbeError(f"could not run ffprobe: {exc}") from exc
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", "replace").strip()[-_MAX_ERROR_CHARS:]
        raise ProbeError(message or f"ffprobe exited with code {completed.returncode}")
    try:
        data = json.loads(completed.stdout or b"{}")
    except json.JSONDecodeError as exc:
        raise ProbeError("ffprobe returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise ProbeError("ffprobe returned unexpected output")
    return data


def probe_raw(path: Path, ffprobe: str = "ffprobe", timeout: float = 120) -> dict[str, Any]:
    """Stream and format information as ffprobe's JSON."""
    return _run(
        [
            ffprobe,
            "-hide_banner",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            ffmpeg_input(path),
        ],
        timeout,
    )


def first_frame_side_data(
    path: Path, ffprobe: str = "ffprobe", timeout: float = 120
) -> list[dict[str, Any]]:
    """Side data of the first video frame (needed to spot HDR10+ metadata)."""
    data = _run(
        [
            ffprobe,
            "-hide_banner",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-read_intervals",
            "%+#1",
            "-show_entries",
            "frame=side_data_list",
            "-of",
            "json",
            ffmpeg_input(path),
        ],
        timeout,
    )
    frames = data.get("frames") or []
    side: list[dict[str, Any]] = frames[0].get("side_data_list") or [] if frames else []
    return side


def probe(path: Path, ffprobe: str = "ffprobe", timeout: float = 120) -> MediaInfo:
    raw = probe_raw(path, ffprobe, timeout)
    frame_side: list[dict[str, Any]] = []
    video = next((s for s in raw.get("streams") or [] if s.get("codec_type") == "video"), None)
    if video is not None and video.get("color_transfer") == "smpte2084":
        try:
            frame_side = first_frame_side_data(path, ffprobe, timeout)
        except ProbeError:
            logger.warning("could not read HDR frame metadata", extra={"path": str(path)})
    return parse(raw, frame_side)
