"""Build a profile that reproduces a sample file (ARCHITECTURE.md §7.2). Pure functions.

What the sample's encoder recorded (x264/x265 write their full settings into
the video stream) is *read*; what it didn't is *estimated* from bits per pixel
using the 0.4 calibration measurements (docs/calibration/quality-0.4.md).
Resolution is never capped (owner decision, phase 0.5 plan).
"""

import math
import re
from typing import Literal

from pydantic import BaseModel

from reelhaven.audio_rules import AudioCodec, is_lossless, is_object_audio
from reelhaven.media.info import MediaInfo, Stream
from reelhaven.profiles import ProfileSettings
from reelhaven.quality import quality_value

Source = Literal["read", "estimated", "default"]
VideoCodec = Literal["hevc", "av1", "h264"]

# Median bits per pixel per frame of x265 / x264 at each level's CRF, over the
# calibration clips (1080p film, animation and CGI). Content varies 2-3x.
_HEVC_BPP = [0.0146, 0.0166, 0.0218, 0.0298, 0.0350, 0.0412, 0.0574, 0.0802, 0.0948, 0.1120]
_H264_BPP = [0.0297, 0.0342, 0.0393, 0.0458, 0.0534, 0.0740, 0.0874, 0.1032, 0.1220, 0.1443]
# Not measured: AV1 needs about 25 % fewer bits than HEVC; older codecs (MPEG-2,
# MPEG-4, VC-1) about 2x H.264.
_BPP: dict[str, list[float]] = {
    "hevc": _HEVC_BPP,
    "h264": _H264_BPP,
    "av1": [b * 0.75 for b in _HEVC_BPP],
    "vp9": _HEVC_BPP,
    "legacy": [b * 2 for b in _H264_BPP],
}
# GPU encoders need more bits for the same quality (calibration 0.4).
_GPU_OVERHEAD = {"nvenc": 1.15, "qsv": 1.55}
_VIDEO_CODECS: dict[str, VideoCodec] = {"hevc": "hevc", "av1": "av1", "h264": "h264"}
# Sample audio a profile can reproduce (AC-3 becomes its successor, E-AC-3).
_AUDIO_TARGETS: dict[str, AudioCodec] = {
    "eac3": "eac3",
    "ac3": "eac3",
    "aac": "aac",
    "opus": "opus",
}

_X265 = re.compile(r"x265 \(build \d+\).*?options: (.+)")
_X264 = re.compile(r"x264 - core \d+.*?options: (.+)")
_OPTION = re.compile(r"([a-z0-9_-]+)=([^ ]+)")


class MimicReport(BaseModel):
    settings: ProfileSettings
    sources: dict[str, Source]  # profile field -> where its value came from
    notes: list[str]
    sample: dict[str, str | int | float | None]


def parse_encoder_settings(text: str) -> tuple[str, dict[str, str]] | None:
    """("x265" or "x264", options) from an encoder's settings string, if present."""
    for name, pattern in (("x265", _X265), ("x264", _X264)):
        match = pattern.search(text)
        if match:
            return name, dict(_OPTION.findall(match.group(1)))
    return None


def level_from_crf(codec: Literal["hevc", "h264"], crf: float) -> int:
    """The 1-10 level whose CPU value is closest to ``crf`` (ties: higher quality)."""
    return min(range(1, 11), key=lambda lv: (abs(quality_value("cpu", codec, lv) - crf), -lv))


def level_from_bpp(codec: str, bpp: float) -> int:
    """The level whose typical bits per pixel is closest (on a log scale)."""
    table = _BPP.get(codec, _BPP["legacy"])
    return min(range(1, 11), key=lambda lv: abs(math.log(table[lv - 1] / max(bpp, 1e-6))))


def _gpu_family(encoder_tag: str | None) -> str | None:
    tag = (encoder_tag or "").lower()
    return next((family for family in _GPU_OVERHEAD if family in tag), None)


def _video_bitrate(info: MediaInfo, video: Stream) -> int | None:
    if video.bit_rate:
        return video.bit_rate
    if not info.size_bytes or not info.duration_s:
        return None
    audio = sum(s.bit_rate or 0 for s in info.streams if s.kind == "audio")
    return max(int(info.size_bytes * 8 / info.duration_s) - audio, 0) or None


def _main_audio(info: MediaInfo) -> Stream | None:
    audio = info.of_kind("audio")
    return next((s for s in audio if s.default), audio[0] if audio else None)


def analyse(
    info: MediaInfo, settings_text: str | None, encoder_tag: str | None = None
) -> MimicReport:
    """A profile reproducing ``info``. ``settings_text``: the text found in the first
    video packets (x264/x265 settings); ``encoder_tag``: the stream's ENCODER tag."""
    video = info.video
    if video is None:
        raise ValueError("the sample has no video")
    sources: dict[str, Source] = {}
    notes: list[str] = []

    # Codec: the sample's, when ReelHaven can produce it.
    codec: VideoCodec = _VIDEO_CODECS.get(video.codec or "", "hevc")
    if video.codec in _VIDEO_CODECS:
        sources["codec"] = "read"
    else:
        sources["codec"] = "default"
        notes.append(f"The sample is {(video.codec or '?').upper()}; HEVC is used instead.")

    ten_bit = codec != "h264" and (video.bit_depth or 8) >= 10
    sources["ten_bit"] = "read" if video.bit_depth else "default"

    # Quality: read the CRF if the encoder recorded one, else estimate.
    parsed = parse_encoder_settings(settings_text or "")
    crf: float | None = None
    if parsed:
        name, options = parsed
        notes.append(f"Encoded with {name}.")
        try:
            crf = float(options["crf"]) if options.get("rc", "crf") == "crf" else None
        except (KeyError, ValueError):
            crf = None
    bitrate = _video_bitrate(info, video)
    fps = video.frame_rate or 24.0
    bpp = (
        bitrate / ((video.width or 0) * (video.height or 0) * fps)
        if bitrate and video.width and video.height
        else None
    )
    if crf is not None and parsed:
        crf_codec: Literal["hevc", "h264"] = "hevc" if parsed[0] == "x265" else "h264"
        quality = level_from_crf(crf_codec, crf)
        sources["quality"] = "read"
        notes.append(f"Quality read from its settings: CRF {crf:g}.")
    elif bpp is not None:
        family = _gpu_family(encoder_tag)
        effective = bpp / _GPU_OVERHEAD[family] if family else bpp
        legacy = video.codec not in _BPP
        quality = level_from_bpp("legacy" if legacy else video.codec or "hevc", effective)
        sources["quality"] = "estimated"
        notes.append(
            "Quality estimated from the bitrate"
            + (f" (made by a GPU encoder, {family.upper()})" if family else "")
            + ". Content matters a lot, so check it with a test run."
        )
    else:
        quality = 6
        sources["quality"] = "default"
        notes.append("The bitrate is unknown, so the quality is the default (Balanced).")

    # Audio: reproduce a compact main track; keep lossless, object or exotic audio.
    audio_mode: Literal["copy", "convert"] = "copy"
    audio_codec: AudioCodec = "eac3"
    per_channel: int | None = None
    main = _main_audio(info)
    sources["audio"] = "default"
    if main is not None and not is_lossless(main) and not is_object_audio(main):
        target = _AUDIO_TARGETS.get(main.codec or "")
        if target and main.bit_rate:
            audio_mode, audio_codec = "convert", target
            channels = main.channels or 2
            per_channel = max(16, min(256, round(main.bit_rate / 1000 / channels)))
            sources["audio"] = "read"
            notes.append(
                f"Audio: {target.upper()} at about {per_channel} kbit/s per channel, like the "
                "sample; bigger tracks in your library will be converted to match."
            )
    if sources["audio"] == "default":
        notes.append("Audio is copied unchanged.")

    settings = ProfileSettings(
        codec=codec,
        quality=quality,
        ten_bit=ten_bit,
        audio=audio_mode,
        audio_codec=audio_codec,
        audio_kbps_per_channel=per_channel,
    )
    sample = {
        "codec": video.codec,
        "width": video.width,
        "height": video.height,
        "bit_depth": video.bit_depth,
        "hdr": video.hdr,
        "video_kbps": round(bitrate / 1000) if bitrate else None,
        "bits_per_pixel": round(bpp, 4) if bpp else None,
        "encoder": parsed[0] if parsed else (encoder_tag or None),
        "audio": f"{main.codec} {main.channels}ch" if main else None,
    }
    return MimicReport(settings=settings, sources=sources, notes=notes, sample=sample)
