"""Should the video be re-encoded? (ARCHITECTURE.md §7.4). Pure functions."""

import hashlib
import json
from typing import Literal

from pydantic import BaseModel

from reelhaven.media.info import MediaInfo, Stream
from reelhaven.profiles import ProfileSettings

# Expected bits per pixel per frame for HEVC at quality level 1..10; AV1 and
# H.264 scale from it. Starting values, refined from test runs (§16).
_HEVC_BPP = [0.022, 0.026, 0.030, 0.035, 0.044, 0.055, 0.068, 0.085, 0.105, 0.130]
_CODEC_FACTOR = {"hevc": 1.0, "av1": 0.75, "h264": 1.6}
# Don't re-encode a file that is already within 15 % of the target bitrate.
_EFFICIENT_MARGIN = 1.15

VideoDecision = Literal["encode", "keep"]


class VideoPlan(BaseModel):
    decision: VideoDecision
    reason: str
    codec: str | None = None
    ten_bit: bool | None = None
    height_before: int | None = None
    height_after: int | None = None
    bitrate_before: int | None = None
    bitrate_target: int | None = None
    bytes_before: int | None = None
    bytes_after_estimate: int | None = None
    savings_percent: float | None = None


def profile_fingerprint(profile: ProfileSettings) -> str:
    """Short hash of everything in a profile that changes the encoded video."""
    data = profile.model_dump(include={"codec", "quality", "speed", "ten_bit", "max_height"})
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:8]


def encode_marker(profile: ProfileSettings) -> str:
    return f"encode-1:{profile_fingerprint(profile)}"


def expected_bitrate(codec: str, quality: float, width: int, height: int, fps: float) -> int:
    low = _HEVC_BPP[int(quality) - 1]
    high = _HEVC_BPP[min(int(quality), len(_HEVC_BPP) - 1)]
    bpp = (low + (high - low) * (quality - int(quality))) * _CODEC_FACTOR[codec]
    return int(bpp * width * height * fps)


def scaled_size(video: Stream, profile: ProfileSettings) -> tuple[int, int]:
    width, height = video.width or 0, video.height or 0
    if profile.max_height and height > profile.max_height:
        width = round(width * profile.max_height / height / 2) * 2
        height = profile.max_height
    return width, height


def format_size(n: int) -> str:
    """Bytes as the UI shows them: 1.0 GB, 120 MB (decimal units)."""
    value, unit = float(n), 0
    units = ("B", "KB", "MB", "GB", "TB")
    while value >= 1000 and unit < len(units) - 1:
        value /= 1000
        unit += 1
    return f"{value:.{0 if value >= 100 or unit == 0 else 1}f} {units[unit]}"


def video_bitrate(info: MediaInfo, video: Stream) -> int | None:
    total = info.bit_rate or (
        int(info.size_bytes * 8 / info.duration_s) if info.size_bytes and info.duration_s else None
    )
    # A stream's own figure (e.g. an MKV BPS tag) can be stale, left over from an earlier
    # version of the file. More than the whole file can't be right: work it out instead.
    if video.bit_rate and (total is None or video.bit_rate <= total):
        return video.bit_rate
    if total is None:
        return None
    others = sum(
        s.bit_rate or (640_000 if s.kind == "audio" else 0) for s in info.streams if s is not video
    )
    return max(total - others, 0) or None


def plan_video(
    info: MediaInfo, profile: ProfileSettings | None, no_gain_profile: str | None = None
) -> VideoPlan:
    video = info.video
    if profile is None:
        return VideoPlan(decision="keep", reason="No compression profile for this library.")
    if video is None or not video.width or not video.height:
        return VideoPlan(decision="keep", reason="No video stream to encode.")
    if video.hdr == "dolby_vision":
        return VideoPlan(
            decision="keep", reason="Dolby Vision is skipped: re-encoding would break it."
        )
    if video.hdr == "hdr10plus":
        return VideoPlan(
            decision="keep", reason="HDR10+ is skipped: re-encoding would lose its metadata."
        )
    if video.hdr in ("hdr10", "hlg") and profile.codec == "h264":
        return VideoPlan(decision="keep", reason="HDR can't be kept in H.264.")
    if no_gain_profile is not None and no_gain_profile == profile_fingerprint(profile):
        return VideoPlan(
            decision="keep", reason="Encoding with this profile was tried and didn't save enough."
        )
    marker = info.tags.get("reelhaven", "")
    if marker == encode_marker(profile):
        return VideoPlan(decision="keep", reason="Already encoded by ReelHaven with this profile.")

    fps = video.frame_rate or 24.0
    width, height = scaled_size(video, profile)
    target = expected_bitrate(profile.codec, profile.quality, width, height, fps)
    current = video_bitrate(info, video)
    base = VideoPlan(
        decision="keep",
        reason="",
        codec=profile.codec,
        ten_bit=(profile.ten_bit or video.hdr in ("hdr10", "hlg")) and profile.codec != "h264",
        height_before=video.height,
        height_after=height,
        bitrate_before=current,
        bitrate_target=target,
        bytes_before=info.size_bytes,
    )
    if current is None or not info.duration_s or not info.size_bytes:
        base.reason = "The video's size is unknown, so savings can't be estimated."
        return base

    scaling = height < video.height
    if video.codec == profile.codec and current <= target * _EFFICIENT_MARGIN and not scaling:
        base.reason = f"Already {profile.codec.upper()} at a low bitrate."
        return base

    video_bytes_after = int(min(target, current) * info.duration_s / 8)
    video_bytes_before = int(current * info.duration_s / 8)
    estimate = max(info.size_bytes - video_bytes_before + video_bytes_after, 0)
    savings = round(100 * (1 - estimate / info.size_bytes), 1)
    base.bytes_after_estimate = estimate
    base.savings_percent = savings
    if savings < profile.min_savings_percent:
        minimum = profile.min_savings_percent
        base.reason = (
            f"Would save only about {format_size(info.size_bytes - estimate)} "
            f"({savings:.0f} %), below the {minimum} % minimum."
        )
        return base
    base.decision = "encode"
    base.reason = f"Saves about {format_size(info.size_bytes - estimate)} ({savings:.0f} %)."
    return base
