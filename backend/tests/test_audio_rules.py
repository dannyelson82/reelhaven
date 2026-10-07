import pytest

from reelhaven.audio_rules import (
    Conversion,
    conversion,
    is_lossless,
    is_object_audio,
    target_kbps,
)
from reelhaven.media.info import Stream


def a(
    codec: str,
    channels: int = 6,
    kbps: int | None = None,
    profile: str | None = None,
    title: str | None = None,
) -> Stream:
    return Stream(
        index=1,
        kind="audio",
        codec=codec,
        channels=channels,
        bit_rate=kbps * 1000 if kbps else None,
        profile=profile,
        title=title,
    )


def test_lossless_and_object_audio() -> None:
    assert is_lossless(a("truehd")) and is_lossless(a("flac")) and is_lossless(a("pcm_s24le"))
    assert is_lossless(a("dts", profile="DTS-HD MA"))
    assert not is_lossless(a("dts", profile="DTS"))
    assert is_object_audio(a("truehd", profile="Dolby TrueHD + Dolby Atmos"))
    assert is_object_audio(a("eac3", profile="Dolby Digital Plus + Dolby Atmos"))
    assert is_object_audio(a("dts", profile="DTS-HD MA + DTS:X"))
    assert is_object_audio(a("truehd", title="English Atmos 7.1"))
    assert not is_lossless(a("truehd", profile="Dolby TrueHD + Dolby Atmos"))


def test_target_bitrate_is_channel_aware_and_capped() -> None:
    assert target_kbps("aac", 2, None) == 128
    assert target_kbps("aac", 6, None) == 384
    assert target_kbps("opus", 8, None) == 384
    assert target_kbps("eac3", 6, None) == 640  # 6 x 112 = 672, E-AC-3 tops out at 640
    assert target_kbps("eac3", 2, 96) == 192
    assert target_kbps("aac", 0, None) == 64  # unknown channels count as one


def test_copy_mode_converts_nothing() -> None:
    assert conversion(a("truehd"), "copy", "eac3", None) is None


def test_compress_lossless_only_touches_lossless() -> None:
    assert kbps(conversion(a("truehd"), "compress_lossless", "eac3", None)) == 640
    assert conversion(a("dts", kbps=1509), "compress_lossless", "eac3", None) is None


@pytest.mark.parametrize(
    ("track", "expected"),
    [
        (a("truehd"), 384),  # lossless: always
        (a("dts", kbps=1509), 384),  # 1509 >= 1.5 x 384
        (a("eac3", kbps=640), 384),  # 640 >= 576
        (a("eac3", kbps=448), None),  # 448 < 576: not worth a lossy-to-lossy pass
        (a("ac3", kbps=None), None),  # unknown bitrate: leave it
        (a("eac3", kbps=768, profile="Dolby Digital Plus + Dolby Atmos"), None),  # objects
        (a("truehd", channels=8), None),  # 7.1 is more than AAC is used for: copied
        (a("aac", channels=2, kbps=192), 128),  # 192 >= 1.5 x 128
        (a("aac", channels=2, kbps=160), None),
    ],
)
def test_convert_rules(track: Stream, expected: int | None) -> None:
    assert kbps(conversion(track, "convert", "aac", None)) == expected


def test_opus_keeps_7_1() -> None:
    assert kbps(conversion(a("truehd", channels=8), "convert", "opus", None)) == 384


def test_only_audio_streams() -> None:
    video = Stream(index=0, kind="video", codec="hevc")
    assert conversion(video, "convert", "aac", None) is None


def kbps(change: Conversion | None) -> int | None:
    return change.kbps if change else None


@pytest.mark.parametrize(
    "track",
    [
        a("truehd"),
        a("truehd", channels=8, profile="Dolby TrueHD + Dolby Atmos"),  # ADR-0024: Atmos too
        a("dts", kbps=1509, profile="DTS-HD MA + DTS:X"),
        a("eac3", kbps=448),  # even a small lossy surround track: stereo was asked for
    ],
)
def test_downmix_turns_surround_into_stereo(track: Stream) -> None:
    assert conversion(track, "convert", "aac", None, downmix=True) == Conversion(128, 2)
    assert conversion(track, "compress_lossless", "opus", 64, downmix=True) == Conversion(128, 2)


def test_downmix_leaves_stereo_to_the_usual_rules() -> None:
    small = a("aac", channels=2, kbps=160)
    assert conversion(small, "convert", "aac", None, downmix=True) is None
    assert conversion(a("flac", channels=2), "convert", "aac", None, downmix=True) == Conversion(
        128
    )


def test_downmix_needs_a_converting_profile() -> None:
    assert conversion(a("truehd"), "copy", "aac", None, downmix=True) is None
