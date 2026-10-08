"""The verifier (ARCHITECTURE.md §6.7): a new file must pass every check
before it may replace the original."""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from reelhaven.media.info import MediaInfo
from reelhaven.media.probe import ProbeError, ffmpeg_input, probe

DECODE_SECONDS = 2.0
# The decode test writes to ffmpeg's null muxer. Right after seeking into the middle of a
# file, the first decoded frames can share a timestamp, which only that throwaway output
# complains about; the file itself is fine (its own muxer refused such timestamps).
_NULL_MUXER_DTS = re.compile(
    r"^\[null @ 0x[0-9a-f]+\] Application provided invalid, non monotonically increasing dts"
)


def decode_errors(stderr: str) -> str:
    """The decode test's error output without the null muxer's timestamp complaints."""
    lines = [line for line in stderr.splitlines() if not _NULL_MUXER_DTS.match(line.strip())]
    return "\n".join(lines).strip()


class VerificationError(Exception):
    pass


@dataclass(frozen=True)
class ExpectedVideo:
    """For encodes: what the new video stream must be. Remuxes pass None (unchanged)."""

    codec: str
    height: int  # the planned output height (source height when not scaled)


def verify_output(
    output: Path,
    source_info: MediaInfo,
    expected: list[tuple[str, str | None, bool | None]],
    ffmpeg: str,
    ffprobe: str,
    timeout_s: float = 300,
    expected_video: ExpectedVideo | None = None,
    expected_codecs: dict[int, tuple[str, int | None]] | None = None,
) -> MediaInfo:
    """Raise VerificationError unless ``output`` is a sound replacement."""
    try:
        info = probe(output, ffprobe, timeout_s)
    except ProbeError as exc:
        raise VerificationError(f"the new file can't be read: {exc}") from exc

    # 1. Stream layout matches the plan.
    actual = [(s.kind, s.language, s.default) for s in info.streams]
    if len(actual) != len(expected):
        raise VerificationError(f"expected {len(expected)} streams, found {len(actual)}")
    for position, ((kind, language, default), (a_kind, a_language, a_default)) in enumerate(
        zip(expected, actual, strict=True)
    ):
        # A video track's language is never planned or changed and players ignore it, but
        # some sources come back tagged after a rewrite (untagged -> "eng"). Audio and
        # subtitle languages decide what is kept, so they must match exactly.
        if kind != a_kind or (kind != "video" and language != a_language):
            raise VerificationError(
                f"stream {position}: expected {kind} {language}, found {a_kind} {a_language}"
            )
        if default is not None and default != a_default:
            raise VerificationError(f"stream {position}: default flag not set as planned")
    for position, (codec, channels) in (expected_codecs or {}).items():
        found = info.streams[position]
        if found.codec != codec:
            raise VerificationError(
                f"stream {position}: expected {codec} audio, found {found.codec}"
            )
        if channels is not None and found.channels != channels:
            raise VerificationError(
                f"stream {position}: expected {channels} channels, found {found.channels}"
            )

    # 2. Video unchanged (a remux must not lose HDR or Dolby Vision).
    src_video, out_video = source_info.video, info.video
    if (src_video is None) != (out_video is None):
        raise VerificationError("the video stream is missing")
    if src_video is not None and out_video is not None:
        if expected_video is None:
            if (src_video.codec, src_video.width, src_video.height) != (
                out_video.codec,
                out_video.width,
                out_video.height,
            ):
                raise VerificationError("the video stream changed")
        elif (out_video.codec, out_video.height) != (expected_video.codec, expected_video.height):
            raise VerificationError(
                f"expected {expected_video.codec} {expected_video.height}p video, "
                f"found {out_video.codec} {out_video.height}p"
            )
        if src_video.hdr != out_video.hdr:
            raise VerificationError(f"HDR metadata changed ({src_video.hdr} -> {out_video.hdr})")

    # 3. Duration within ±1 s or 0.5 %.
    if source_info.duration_s and info.duration_s is not None:
        tolerance = max(1.0, source_info.duration_s * 0.005)
        if abs(source_info.duration_s - info.duration_s) > tolerance:
            raise VerificationError(
                f"duration changed from {source_info.duration_s:.1f}s to {info.duration_s:.1f}s"
            )
    elif source_info.duration_s:
        raise VerificationError("the new file has no duration")

    # 4. Decode test: short segments at the start, middle and end.
    duration = info.duration_s or 0.0
    points = sorted({0.0, max(duration / 2 - 1, 0.0), max(duration - DECODE_SECONDS - 1, 0.0)})
    for start in points:
        _decode(ffmpeg, output, start, timeout_s)
    return info


def _decode(ffmpeg: str, path: Path, start: float, timeout_s: float) -> None:
    args = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-v",
        "error",
        "-ss",
        f"{start:.3f}",
        "-i",
        ffmpeg_input(path),
        "-t",
        str(DECODE_SECONDS),
        "-map",
        "0:v:0?",
        "-map",
        "0:a?",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(  # noqa: S603 - argument list, no shell
            args, capture_output=True, timeout=timeout_s, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise VerificationError("decode test timed out") from exc
    errors = decode_errors(result.stderr.decode("utf-8", "replace"))
    if result.returncode != 0 or errors:
        raise VerificationError(f"decode test failed at {start:.0f}s: {errors[-500:]}")
