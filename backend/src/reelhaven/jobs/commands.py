"""ffmpeg command builders (ARCHITECTURE.md §6.6). Pure functions returning
argument lists, never shell strings (SECURITY.md)."""

from pathlib import Path

from reelhaven.audio_rules import ENCODER, AudioCodec
from reelhaven.media.info import MediaInfo, Stream
from reelhaven.media.probe import ffmpeg_input
from reelhaven.planner import Plan

MARKER_TAG = "REELHAVEN"
MARKER_VALUE = "remux-1"

# Containers a remux may write in phase 0.3 (ADR-0018: same as the input).
REMUX_FORMATS = {".mkv": "matroska", ".mp4": "mp4", ".m4v": "mp4", ".mov": "mov"}
_MP4_FAMILY = {"mp4", "mov"}
# Dispositions ReelHaven manages; everything else on a stream is preserved.
_MANAGED = {"default"}


class UnsupportedContainerError(ValueError):
    pass


def remux_format(path: Path) -> str:
    fmt = REMUX_FORMATS.get(path.suffix.lower())
    if fmt is None:
        raise UnsupportedContainerError(
            f"remuxing {path.suffix or 'this'} files isn't supported yet"
        )
    return fmt


def _kept_streams(info: MediaInfo, plan: Plan, fmt: str) -> list[tuple[Stream, bool | None]]:
    """Streams to copy, in source order, with the planned default flag (None = untouched)."""
    planned = {t.index: t for t in plan.tracks}
    kept: list[tuple[Stream, bool | None]] = []
    for stream in info.streams:
        track = planned.get(stream.index)
        if track is not None:
            if track.keep:
                kept.append((stream, track.default_after))
        elif stream.kind in ("video", "attachment"):
            kept.append((stream, None))
        elif stream.kind == "data" and fmt in _MP4_FAMILY:
            kept.append((stream, None))  # e.g. MP4 timecode tracks; Matroska can't hold them
    return kept


def _disposition(stream: Stream, default: bool) -> str:
    flags = sorted(
        {d for d in stream.dispositions if d not in _MANAGED} | ({"default"} if default else set())
    )
    return "+".join(flags) if flags else "0"


def remux_command(
    ffmpeg: str, source: Path, output: Path, info: MediaInfo, plan: Plan
) -> list[str]:
    """Copy the kept streams of ``source`` into ``output`` with the planned defaults."""
    fmt = remux_format(source)
    if remux_format(output) != fmt:
        raise ValueError("a remux keeps the container (ADR-0018)")
    kept = _kept_streams(info, plan, fmt)
    args = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-nostats",
        "-i",
        ffmpeg_input(source),
    ]
    for stream, _ in kept:
        args += ["-map", f"0:{stream.index}"]
    args += ["-map_metadata", "0", "-map_chapters", "0", "-c", "copy"]
    for out_index, (stream, default) in enumerate(kept):
        if default is not None:
            args += [f"-disposition:{out_index}", _disposition(stream, default)]
    args += _audio_conversion_args(kept, plan, fmt)
    args += ["-metadata", f"{MARKER_TAG}={MARKER_VALUE}"]
    if fmt in _MP4_FAMILY:
        args += ["-movflags", "+faststart+use_metadata_tags"]
    args += ["-f", fmt, ffmpeg_input(output)]
    return args


def expected_layout(
    source: Path, info: MediaInfo, plan: Plan
) -> list[tuple[str, str | None, bool | None]]:
    """(kind, language, default) of each output stream, for the verifier."""
    return [
        (stream.kind, stream.language, default)
        for stream, default in _kept_streams(info, plan, remux_format(source))
    ]


_MKV_STAT_TAGS = ("BPS", "NUMBER_OF_BYTES", "NUMBER_OF_FRAMES", "DURATION", "_STATISTICS_TAGS")
_PROBED_CODEC: dict[AudioCodec, str] = {"eac3": "eac3", "aac": "aac", "opus": "opus"}


def _audio_conversion_args(
    kept: list[tuple[Stream, bool | None]], plan: Plan, fmt: str
) -> list[str]:
    """ADR-0023: re-encode the audio tracks the plan converts; everything else is copied."""
    converts = {t.index: t for t in plan.tracks if t.convert_codec and t.convert_kbps}
    args: list[str] = []
    audio_index = 0
    for out_index, (stream, _) in enumerate(kept):
        if stream.kind != "audio":
            continue
        track = converts.get(stream.index)
        if track is not None and track.convert_codec is not None:
            codec = track.convert_codec
            args += [f"-c:a:{audio_index}", ENCODER[codec], f"-b:a:{audio_index}"]
            args += [f"{track.convert_kbps}k"]
            if track.convert_channels:
                args += [f"-ac:a:{audio_index}", str(track.convert_channels)]
            if codec == "opus":
                args += [f"-mapping_family:a:{audio_index}", "1"]
            if fmt == "matroska":
                # The old track's bitrate would make the next plan convert it again.
                for tag in _MKV_STAT_TAGS:
                    args += [f"-metadata:s:{out_index}", f"{tag}="]
        audio_index += 1
    return args


def expected_remux_codecs(
    source: Path, info: MediaInfo, plan: Plan
) -> dict[int, tuple[str, int | None]]:
    """Output position -> (codec, channels or None) of every converted audio track."""
    tracks = {t.index: t for t in plan.tracks}
    out: dict[int, tuple[str, int | None]] = {}
    for position, (stream, _) in enumerate(_kept_streams(info, plan, remux_format(source))):
        track = tracks.get(stream.index)
        if track is not None and track.convert_codec is not None:
            out[position] = (_PROBED_CODEC[track.convert_codec], track.convert_channels)
    return out
