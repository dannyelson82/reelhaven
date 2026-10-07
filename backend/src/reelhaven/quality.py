"""One quality scale, mapped to each encoder's own knob (ADR-0019).

Level 1 = smallest files, 10 = closest to the source. Starting tables; they
are refined from test-run measurements (ARCHITECTURE.md §16).
"""

from reelhaven.encoders import Codec, Family

# x265 / x264 CRF-like values (lower = better) per quality level 1..10.
_HEVC: list[float] = [31, 29.5, 28, 26.5, 25, 23.5, 22, 20.5, 19, 18]
_H264: list[float] = [28, 27, 26, 25, 24, 22.5, 21, 20, 19, 18]
# AV1 encoders use a larger scale.
_AV1: list[float] = [46, 43, 40, 38, 36, 34, 31, 29, 27, 25]

# Hardware encoders need a slightly better (lower) value than x265 for a similar
# result; the offset is per family.
_FAMILY_OFFSET: dict[Family, float] = {"cpu": 0, "nvenc": 1, "qsv": 0, "vaapi": 0}


def quality_value(family: Family, codec: Codec, level: int) -> int:
    """The encoder-specific value for a 1-10 quality level (lower = better)."""
    if not 1 <= level <= 10:
        raise ValueError("quality level must be 1-10")
    tables: dict[str, list[float]] = {"hevc": _HEVC, "h264": _H264, "av1": _AV1}
    table = tables[codec]
    value = table[level - 1] + _FAMILY_OFFSET[family]
    return max(1, round(value))
