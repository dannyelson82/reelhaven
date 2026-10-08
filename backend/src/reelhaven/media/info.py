"""The normalised description of a media file (ARCHITECTURE.md §6.2)."""

import re
from typing import Any, Literal

from pydantic import BaseModel

from reelhaven.media.languages import normalise

StreamKind = Literal["video", "audio", "subtitle", "attachment", "data"]
HdrType = Literal["sdr", "hdr10", "hdr10plus", "hlg", "dolby_vision"]

# Subtitles stored as pictures: kept as-is (no OCR in v1, ARCHITECTURE.md §8.2).
IMAGE_SUBTITLE_CODECS = frozenset({"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"})

_FORCED_TITLE = re.compile(r"\bforced\b", re.IGNORECASE)
_SDH_TITLE = re.compile(r"\b(sdh|cc|hearing[ -]impaired)\b", re.IGNORECASE)
_COMMENTARY_TITLE = re.compile(r"\bcommentar(y|ies)\b", re.IGNORECASE)


class Stream(BaseModel):
    index: int
    kind: StreamKind
    codec: str | None = None
    profile: str | None = None
    language: str | None = None  # canonical (languages.normalise); None = untagged
    raw_language: str | None = None
    title: str | None = None
    default: bool = False
    forced: bool = False
    hearing_impaired: bool = False
    commentary: bool = False
    # Every disposition flag ffprobe reported as set ("default", "forced",
    # "attached_pic"...), so a remux can preserve them exactly.
    dispositions: list[str] = []
    bit_rate: int | None = None
    # video
    width: int | None = None
    height: int | None = None
    bit_depth: int | None = None
    pix_fmt: str | None = None  # e.g. "yuv420p10le"; None in scans before ADR-0029
    frame_rate: float | None = None
    hdr: HdrType | None = None
    # audio
    channels: int | None = None
    channel_layout: str | None = None
    sample_rate: int | None = None
    # subtitle
    image_based: bool = False


class MediaInfo(BaseModel):
    container: str
    duration_s: float | None
    size_bytes: int | None
    bit_rate: int | None
    streams: list[Stream]
    tags: dict[str, str] = {}

    def of_kind(self, kind: StreamKind) -> list[Stream]:
        return [s for s in self.streams if s.kind == kind]

    @property
    def video(self) -> Stream | None:
        videos = [s for s in self.of_kind("video") if s.codec not in _COVER_ART_CODECS]
        return videos[0] if videos else None


# Embedded cover pictures show up as video streams.
_COVER_ART_CODECS = frozenset({"mjpeg", "png", "bmp", "gif"})


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _frame_rate(value: Any) -> float | None:
    if not isinstance(value, str) or "/" not in value:
        return _float(value)
    num, den = value.split("/", 1)
    n, d = _float(num), _float(den)
    return round(n / d, 3) if n is not None and d else None


def _bit_depth(raw: dict[str, Any]) -> int | None:
    depth = _int(raw.get("bits_per_raw_sample"))
    if depth:
        return depth
    pix_fmt = str(raw.get("pix_fmt") or "")
    match = re.search(r"p(9|10|12|14|16)(le|be)?$", pix_fmt)
    if match:
        return int(match.group(1))
    return 8 if pix_fmt else None


def _hdr(raw: dict[str, Any], frame_side_data: list[dict[str, Any]]) -> HdrType:
    side_types = {str(d.get("side_data_type", "")) for d in raw.get("side_data_list") or []}
    if any("DOVI" in t or "Dolby Vision" in t for t in side_types):
        return "dolby_vision"
    transfer = raw.get("color_transfer")
    if transfer == "arib-std-b67":
        return "hlg"
    if transfer == "smpte2084":
        frame_types = {str(d.get("side_data_type", "")) for d in frame_side_data}
        if any("2094-40" in t or "HDR10+" in t for t in frame_types):
            return "hdr10plus"
        return "hdr10"
    return "sdr"


def _kind(codec_type: Any) -> StreamKind:
    if codec_type in ("video", "audio", "subtitle", "attachment"):
        return codec_type  # type: ignore[no-any-return]
    return "data"


def _tag(tags: dict[str, Any], key: str) -> str | None:
    # Tag keys vary in case between containers ("language", "LANGUAGE").
    for k, v in tags.items():
        if k.lower() == key and v not in (None, ""):
            return str(v)
    return None


def parse(probe: dict[str, Any], frame_side_data: list[dict[str, Any]] | None = None) -> MediaInfo:
    """Build MediaInfo from ``ffprobe -show_format -show_streams -of json`` output."""
    fmt = probe.get("format") or {}
    streams: list[Stream] = []
    for raw in probe.get("streams") or []:
        tags = raw.get("tags") or {}
        disposition = raw.get("disposition") or {}
        title = _tag(tags, "title")
        raw_language = _tag(tags, "language")
        kind = _kind(raw.get("codec_type"))
        codec = raw.get("codec_name")
        stream = Stream(
            index=int(raw.get("index", len(streams))),
            kind=kind,
            codec=codec,
            profile=raw.get("profile"),
            language=normalise(raw_language),
            raw_language=raw_language,
            title=title,
            default=bool(disposition.get("default")),
            forced=bool(disposition.get("forced")) or bool(title and _FORCED_TITLE.search(title)),
            hearing_impaired=bool(disposition.get("hearing_impaired"))
            or bool(title and _SDH_TITLE.search(title)),
            commentary=bool(disposition.get("comment"))
            or bool(title and _COMMENTARY_TITLE.search(title)),
            bit_rate=_int(raw.get("bit_rate")) or _int(_tag(tags, "bps")),
            dispositions=sorted(k for k, v in disposition.items() if v),
        )
        if kind == "video":
            stream.width = _int(raw.get("width"))
            stream.height = _int(raw.get("height"))
            stream.bit_depth = _bit_depth(raw)
            stream.pix_fmt = raw.get("pix_fmt") or None
            stream.frame_rate = _frame_rate(raw.get("avg_frame_rate")) or _frame_rate(
                raw.get("r_frame_rate")
            )
            stream.hdr = _hdr(raw, frame_side_data or [])
        elif kind == "audio":
            stream.channels = _int(raw.get("channels"))
            stream.channel_layout = raw.get("channel_layout")
            stream.sample_rate = _int(raw.get("sample_rate"))
        elif kind == "subtitle":
            stream.image_based = codec in IMAGE_SUBTITLE_CODECS
        streams.append(stream)

    return MediaInfo(
        container=str(fmt.get("format_name") or "unknown"),
        duration_s=_float(fmt.get("duration")),
        size_bytes=_int(fmt.get("size")),
        bit_rate=_int(fmt.get("bit_rate")),
        streams=streams,
        tags={str(k).lower(): str(v) for k, v in (fmt.get("tags") or {}).items()},
    )
