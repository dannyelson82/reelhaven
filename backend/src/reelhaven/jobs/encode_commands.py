"""ffmpeg command builder for re-encoding (ARCHITECTURE.md §6.6).

The output is described once as a list of OutputStream; the same list builds
the command and tells the verifier what to expect.
"""

from dataclasses import dataclass
from pathlib import Path

from reelhaven.encoders import (
    Codec,
    Device,
    device_select_args,
    encoder_name,
    hw_init_args,
    profile_args,
    upload_filters,
)
from reelhaven.jobs.commands import MARKER_TAG, remux_format
from reelhaven.jobs.verify import ExpectedVideo
from reelhaven.media.info import MediaInfo, Stream
from reelhaven.media.probe import ffmpeg_input
from reelhaven.planner import Plan
from reelhaven.profiles import ProfileSettings
from reelhaven.quality import quality_value

ENCODE_MARKER = "encode-1"
_MP4_FAMILY = {"mp4", "mov"}
_LOSSLESS_AUDIO = {"truehd", "flac", "alac", "mlp"}
_OBJECT_AUDIO_HINTS = ("atmos", "dts:x", "dts-x", "joc")
_EAC3_BITRATE = {1: 128, 2: 224, 3: 384, 4: 448, 5: 640, 6: 640}
_MKV_STAT_TAGS = ("BPS", "NUMBER_OF_BYTES", "NUMBER_OF_FRAMES", "DURATION", "_STATISTICS_TAGS")

_NVENC_PRESET = {"fast": "p3", "balanced": "p5", "slow": "p7"}
_QSV_PRESET = {"fast": "veryfast", "balanced": "medium", "slow": "veryslow"}
_X26X_PRESET = {"fast": "fast", "balanced": "medium", "slow": "slow"}
_SVT_PRESET = {"fast": "8", "balanced": "6", "slow": "4"}


@dataclass(frozen=True)
class OutputStream:
    kind: str
    source_index: int
    action: str  # "copy", "encode-video", "eac3", "aac-stereo"
    language: str | None
    default: bool | None  # None: leave the source flag alone
    dispositions: tuple[str, ...] = ()
    title: str | None = None


def is_lossless(stream: Stream) -> bool:
    codec = (stream.codec or "").lower()
    profile = (stream.profile or "").lower()
    if any(h in profile or h in (stream.title or "").lower() for h in _OBJECT_AUDIO_HINTS):
        return False  # object audio (Atmos, DTS:X) is always copied
    if codec in _LOSSLESS_AUDIO or codec.startswith("pcm_"):
        return True
    return codec == "dts" and "ma" in profile  # DTS-HD MA


def output_streams(
    info: MediaInfo, plan: Plan, profile: ProfileSettings, fmt: str
) -> list[OutputStream]:
    planned = {t.index: t for t in plan.tracks}
    main_video = info.video
    out: list[OutputStream] = []
    stereo_source: Stream | None = None
    for stream in info.streams:
        track = planned.get(stream.index)
        if stream.kind == "video":
            action = "encode-video" if main_video and stream.index == main_video.index else "copy"
            out.append(
                OutputStream("video", stream.index, action, None, None, tuple(stream.dispositions))
            )
        elif stream.kind == "attachment" or (stream.kind == "data" and fmt in _MP4_FAMILY):
            out.append(
                OutputStream(
                    stream.kind, stream.index, "copy", None, None, tuple(stream.dispositions)
                )
            )
        elif track is not None and track.keep:
            action = "copy"
            if (
                stream.kind == "audio"
                and profile.audio == "compress_lossless"
                and is_lossless(stream)
                and (stream.channels or 0) <= 6
            ):
                action = "eac3"
            out.append(
                OutputStream(
                    stream.kind,
                    stream.index,
                    action,
                    stream.language,
                    track.default_after,
                    tuple(stream.dispositions),
                )
            )
            if stream.kind == "audio" and track.default_after:
                stereo_source = stream
    if profile.add_stereo_aac and stereo_source is not None and (stereo_source.channels or 2) > 2:
        last_audio = max(i for i, s in enumerate(out) if s.kind == "audio")
        out.insert(
            last_audio + 1,
            OutputStream(
                "audio",
                stereo_source.index,
                "aac-stereo",
                stereo_source.language,
                False,
                title="Stereo (AAC)",
            ),
        )
    return out


def target_height(source: Stream, profile: ProfileSettings) -> int | None:
    """New height when scaling down; None when the source already fits (never upscale)."""
    if profile.max_height is None or source.height is None or source.height <= profile.max_height:
        return None
    return profile.max_height


def encode_command(
    ffmpeg: str,
    device: Device,
    source: Path,
    output: Path,
    info: MediaInfo,
    plan: Plan,
    profile: ProfileSettings,
) -> list[str]:
    fmt = remux_format(source)
    if remux_format(output) != fmt:
        raise ValueError("an encode keeps the container (ADR-0018)")
    video = info.video
    if video is None:
        raise ValueError("no video stream to encode")
    codec: Codec = profile.codec
    hdr = video.hdr in ("hdr10", "hlg")
    ten_bit = (profile.ten_bit or hdr) and codec != "h264"
    if hdr and codec == "h264":
        raise ValueError("HDR can't be kept in H.264; use HEVC or AV1")
    streams = output_streams(info, plan, profile, fmt)

    args = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-nostats",
    ]
    args += hw_init_args(device)
    args += ["-i", ffmpeg_input(source)]
    for s in streams:
        args += ["-map", f"0:{s.source_index}"]
    args += [
        "-map_metadata",
        "0",
        "-map_chapters",
        "0",
        "-c",
        "copy",
        "-max_muxing_queue_size",
        "4096",
    ]

    # --- video -------------------------------------------------------------------------
    out_video = next(i for i, s in enumerate(streams) if s.action == "encode-video")
    filters: list[str] = []
    height = target_height(video, profile)
    if height is not None:
        filters.append(f"scale=-2:{height}:flags=lanczos")
    filters += upload_filters(device, ten_bit)
    value = quality_value(device.family, codec, profile.quality)
    args += ["-filter:v:0", ",".join(filters), "-c:v:0", encoder_name(device, codec)]
    args += device_select_args(device)
    args += profile_args(device, codec, ten_bit)
    args += _rate_control(device.family, codec, value, profile.speed)
    # Colour tags and HDR side data pass through from the source; the verifier checks them.
    if fmt in _MP4_FAMILY and codec == "hevc":
        args += ["-tag:v:0", "hvc1"]  # needed for Apple players
    if fmt == "matroska":
        for tag in _MKV_STAT_TAGS:
            args += [f"-metadata:s:{out_video}", f"{tag}="]  # stale after re-encoding

    # --- audio -------------------------------------------------------------------------
    audio_index = 0
    for out_index, s in enumerate(streams):
        if s.kind != "audio":
            continue
        if s.action == "eac3":
            channels = (
                next((st.channels for st in info.streams if st.index == s.source_index), 6) or 6
            )
            args += [
                f"-c:a:{audio_index}",
                "eac3",
                f"-b:a:{audio_index}",
                f"{_EAC3_BITRATE.get(channels, 640)}k",
            ]
        elif s.action == "aac-stereo":
            args += [
                f"-c:a:{audio_index}",
                "aac",
                f"-ac:a:{audio_index}",
                "2",
                f"-b:a:{audio_index}",
                "160k",
                f"-metadata:s:{out_index}",
                f"title={s.title}",
            ]
        audio_index += 1

    # --- dispositions --------------------------------------------------------------------
    for out_index, s in enumerate(streams):
        if s.default is not None:
            flags = sorted(
                {d for d in s.dispositions if d != "default"}
                | ({"default"} if s.default else set())
            )
            args += [f"-disposition:{out_index}", "+".join(flags) if flags else "0"]

    args += ["-metadata", f"{MARKER_TAG}={ENCODE_MARKER}"]
    if fmt in _MP4_FAMILY:
        args += ["-movflags", "+faststart+use_metadata_tags"]
    args += ["-f", fmt, ffmpeg_input(output)]
    return args


def _rate_control(family: str, codec: Codec, value: int, speed: str) -> list[str]:
    if family == "nvenc":
        return [
            "-preset",
            _NVENC_PRESET[speed],
            "-tune",
            "hq",
            "-rc",
            "vbr",
            "-cq",
            str(value),
            "-b:v",
            "0",
            "-spatial_aq",
            "1",
            "-rc-lookahead",
            "20",
        ]
    if family == "qsv":
        return ["-preset", _QSV_PRESET[speed], "-global_quality", str(value)]
    if family == "vaapi":
        return ["-rc_mode", "CQP", "-qp", str(value)]
    if codec == "av1":
        return ["-preset", _SVT_PRESET[speed], "-crf", str(value)]
    return ["-preset", _X26X_PRESET[speed], "-crf", str(value)] + (
        ["-x265-params", "log-level=error"] if codec == "hevc" else []
    )


def expected_encode_layout(
    source: Path, info: MediaInfo, plan: Plan, profile: ProfileSettings
) -> list[tuple[str, str | None, bool | None]]:
    return [
        (s.kind, s.language, s.default)
        for s in output_streams(info, plan, profile, remux_format(source))
    ]


def expected_video(info: MediaInfo, profile: ProfileSettings) -> ExpectedVideo:
    video = info.video
    if video is None or video.height is None:
        raise ValueError("no video stream to encode")
    return ExpectedVideo(codec=profile.codec, height=target_height(video, profile) or video.height)
