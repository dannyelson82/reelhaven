"""What made a video stream: x264/x265 settings strings and ENCODER tags (for mimic)."""

import re
import subprocess
from pathlib import Path

from reelhaven.cpu_limit import preexec
from reelhaven.media.probe import ffmpeg_input, probe_raw

_RAW_FORMAT = {"hevc": "hevc", "h264": "h264"}  # only these carry the settings in SEI
_SETTINGS = re.compile(rb"x26[45][ -~]{20,}options: [ -~]+")
_MAX_BYTES = 32 * 1024 * 1024


def read_settings_string(
    ffmpeg: str, path: Path, codec: str | None, timeout: float = 120
) -> str | None:
    """The x264/x265 settings text from the first video frames, if the encoder wrote it."""
    fmt = _RAW_FORMAT.get(codec or "")
    if fmt is None:
        return None
    args = [
        ffmpeg, "-hide_banner", "-nostdin", "-v", "error",
        "-i", ffmpeg_input(path),
        "-map", "0:v:0", "-c", "copy", "-frames:v", "3", "-f", fmt, "-",
    ]  # fmt: skip
    try:
        result = subprocess.run(  # noqa: S603 - argument list, no shell
            args, capture_output=True, timeout=timeout, check=False, preexec_fn=preexec()
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = _SETTINGS.search(result.stdout[:_MAX_BYTES])
    return match.group(0).decode("ascii", "replace") if match else None


def read_encoder_tag(path: Path, ffprobe: str = "ffprobe") -> str | None:
    """The video stream's ENCODER tag (e.g. "Lavc61.3.100 hevc_nvenc"), or the file's."""
    raw = probe_raw(path, ffprobe)
    for stream in raw.get("streams", []):
        if stream.get("codec_type") == "video":
            tags = {k.lower(): v for k, v in (stream.get("tags") or {}).items()}
            if tags.get("encoder"):
                return str(tags["encoder"])
            break
    tags = {k.lower(): v for k, v in (raw.get("format", {}).get("tags") or {}).items()}
    return str(tags["encoder"]) if tags.get("encoder") else None
