"""One quality scale, mapped to each encoder's own knob (ADR-0019).

Level 1 = smallest files, 10 = closest to the source. The CPU encoders (x265,
x264, SVT-AV1) are the reference. The NVENC and Quick Sync tables were measured
with ``scripts/calibrate_quality.py`` (docs/calibration/quality-0.4.md): at the
same level, they give the same average XPSNR as the CPU encoder on real film
clips. GPU files come out somewhat larger at the same quality; that is the
price of their speed, not a tuning error.
"""

from reelhaven.encoders import Codec, Family

# Lower value = better quality, per level 1..10.
_CPU: dict[Codec, list[int]] = {
    "hevc": [31, 30, 28, 26, 25, 24, 22, 20, 19, 18],  # x265 -crf
    "h264": [28, 27, 26, 25, 24, 22, 21, 20, 19, 18],  # x264 -crf
    "av1": [46, 43, 40, 38, 36, 34, 31, 29, 27, 25],  # SVT-AV1 -crf (0-63)
}
# Measured on an RTX 3060 (calibration 0.4). AV1 can't be measured on it
# (no AV1 encoder); NVENC uses the same -cq scale for AV1, so it borrows HEVC's.
_NVENC: dict[Codec, list[int]] = {
    "hevc": [36, 35, 33, 31, 30, 29, 27, 25, 24, 23],
    "h264": [33, 32, 31, 30, 29, 27, 26, 25, 24, 23],
}
_NVENC["av1"] = _NVENC["hevc"]
# Measured on an Intel UHD 630 (calibration 0.4); AV1 borrows HEVC's scale.
_QSV: dict[Codec, list[int]] = {
    "hevc": [28, 27, 25, 23, 22, 21, 18, 17, 16, 15],
    "h264": [27, 26, 25, 24, 23, 19, 18, 17, 15, 14],
}
_QSV["av1"] = _QSV["hevc"]

_TABLES: dict[Family, dict[Codec, list[int]]] = {
    "cpu": _CPU,
    "nvenc": _NVENC,
    "qsv": _QSV,
    "vaapi": _CPU,  # AMD: not calibrated yet (no hardware); CPU values as a start
}


def quality_value(family: Family, codec: Codec, level: int) -> int:
    """The encoder-specific value for a 1-10 quality level (lower = better)."""
    if not 1 <= level <= 10:
        raise ValueError("quality level must be 1-10")
    return _TABLES[family][codec][level - 1]
