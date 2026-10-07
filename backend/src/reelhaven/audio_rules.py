"""Which audio tracks a profile converts, and to what (ADR-0023, ADR-0024). Pure functions."""

from dataclasses import dataclass
from typing import Literal

from reelhaven.media.info import Stream

AudioCodec = Literal["eac3", "aac", "opus"]

_LOSSLESS = {"truehd", "flac", "alac", "mlp"}
_OBJECT_HINTS = ("atmos", "dts:x", "dts-x", "joc")
# Most channels each codec is used for; tracks with more are copied (never downmixed).
MAX_CHANNELS: dict[AudioCodec, int] = {"eac3": 6, "aac": 6, "opus": 8}
# Default bitrate per channel (kbit/s) and the codec's ceiling for a whole track.
DEFAULT_KBPS_PER_CHANNEL: dict[AudioCodec, int] = {"eac3": 112, "aac": 64, "opus": 48}
_MAX_TRACK_KBPS: dict[AudioCodec, int] = {"eac3": 640, "aac": 512, "opus": 510}
# A lossy track is only converted when it's at least this much bigger than the target.
LOSSY_FACTOR = 1.5
ENCODER: dict[AudioCodec, str] = {"eac3": "eac3", "aac": "aac", "opus": "libopus"}


def is_object_audio(stream: Stream) -> bool:
    """Atmos / DTS:X: always copied, converting would lose the objects."""
    text = f"{stream.profile or ''} {stream.title or ''}".lower()
    return any(hint in text for hint in _OBJECT_HINTS)


def is_lossless(stream: Stream) -> bool:
    if is_object_audio(stream):
        return False
    codec = (stream.codec or "").lower()
    if codec in _LOSSLESS or codec.startswith("pcm_"):
        return True
    return codec == "dts" and "ma" in (stream.profile or "").lower()  # DTS-HD MA


def target_kbps(codec: AudioCodec, channels: int, per_channel: int | None) -> int:
    per = per_channel or DEFAULT_KBPS_PER_CHANNEL[codec]
    return min(per * max(channels, 1), _MAX_TRACK_KBPS[codec])


@dataclass(frozen=True)
class Conversion:
    kbps: int  # target bitrate of the whole track
    channels: int | None = None  # 2 when downmixing to stereo; None keeps the layout


def conversion(
    stream: Stream,
    mode: Literal["copy", "compress_lossless", "convert"],
    codec: AudioCodec,
    per_channel: int | None,
    downmix: bool = False,
) -> Conversion | None:
    """How to convert this track, or None to copy it (ADR-0023, ADR-0024)."""
    if mode == "copy" or stream.kind != "audio":
        return None
    channels = stream.channels or 2
    if downmix and channels > 2:
        # ADR-0024: the owner asked for stereo; this includes Atmos and DTS:X.
        return Conversion(target_kbps(codec, 2, per_channel), 2)
    if is_object_audio(stream) or channels > MAX_CHANNELS[codec]:
        return None
    target = target_kbps(codec, channels, per_channel)
    if is_lossless(stream):
        return Conversion(target)
    lossy_big = stream.bit_rate is not None and stream.bit_rate >= LOSSY_FACTOR * target * 1000
    if mode == "convert" and lossy_big:
        return Conversion(target)
    return None  # lossy and small enough already, or its bitrate is unknown


def source_bitrate(stream: Stream) -> int | None:
    """The track's bitrate in bit/s, estimated for lossless tracks that don't record it."""
    if stream.bit_rate:
        return stream.bit_rate
    if is_lossless(stream):
        # Lossless audio typically compresses 24-bit PCM to about 60 %.
        return int((stream.channels or 2) * (stream.sample_rate or 48000) * 24 * 0.6)
    return None


def saved_bytes(stream: Stream, target_kbps: int, duration_s: float) -> int:
    """Estimated bytes saved by converting this track (0 when unknown)."""
    before = source_bitrate(stream)
    if before is None:
        return 0
    return max(int((before - target_kbps * 1000) * duration_s / 8), 0)
