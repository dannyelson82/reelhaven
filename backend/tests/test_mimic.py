import os
from pathlib import Path

import pytest

from reelhaven.media.encoder_info import read_encoder_tag, read_settings_string
from reelhaven.media.info import MediaInfo, Stream
from reelhaven.media.probe import probe
from reelhaven.mimic import analyse, level_from_bpp, level_from_crf, parse_encoder_settings
from tests.media_fixtures import FFMPEG, Audio, Spec, make

X265 = (
    "x265 (build 199) - 3.5+1-f0c1022b6:[Linux][GCC 13.2.0][64 bit] 8bit+10bit+12bit - "
    "H.265/HEVC codec - Copyright 2013-2018 (c) Multicoreware, Inc - http://x265.org - "
    "options: cpuid=1111039 frame-threads=3 numa-pools=6 wpp ctu=64 min-cu-size=8 "
    "rc=crf crf=20.0 qcomp=0.60 qpstep=4 stats-write=0 stats-read=0 ipratio=1.40"
)
X264 = (
    "x264 - core 164 r3108 31e19f9 - H.264/MPEG-4 AVC codec - Copyleft 2003-2023 - "
    "http://www.videolan.org/x264.html - options: cabac=1 ref=3 deblock=1:0:0 "
    "rc_lookahead=40 rc=crf mbtree=1 crf=19.0 qcomp=0.60 qpmin=0 qpmax=69"
)
X265_ABR = X265.replace("rc=crf crf=20.0", "rc=abr bitrate=4000")


def sample(
    codec: str = "hevc",
    bit_depth: int = 10,
    video_kbps: int | None = 2500,
    audio: Stream | None = None,
) -> MediaInfo:
    streams = [
        Stream(
            index=0,
            kind="video",
            codec=codec,
            width=1920,
            height=1080,
            frame_rate=24.0,
            bit_depth=bit_depth,
            bit_rate=video_kbps * 1000 if video_kbps else None,
        )
    ]
    if audio is not None:
        streams.append(audio)
    return MediaInfo(
        container="matroska,webm", duration_s=None, size_bytes=None, bit_rate=None, streams=streams
    )


def eac3(kbps: int = 640, channels: int = 6, profile: str | None = None) -> Stream:
    return Stream(
        index=1,
        kind="audio",
        codec="eac3",
        channels=channels,
        bit_rate=kbps * 1000,
        default=True,
        profile=profile,
    )


def test_parse_encoder_settings() -> None:
    name, options = parse_encoder_settings("junk " + X265 + " more") or ("", {})
    assert name == "x265" and options["crf"] == "20.0" and options["rc"] == "crf"
    name, options = parse_encoder_settings(X264) or ("", {})
    assert name == "x264" and options["crf"] == "19.0"
    assert parse_encoder_settings("Lavc62 hevc_nvenc") is None


def test_level_from_crf() -> None:
    assert level_from_crf("hevc", 24) == 6  # Balanced
    assert level_from_crf("hevc", 20) == 8  # High quality
    assert level_from_crf("hevc", 22.5) == 7
    assert level_from_crf("hevc", 14) == 10 and level_from_crf("hevc", 40) == 1
    assert level_from_crf("h264", 19) == 9


def test_level_from_bpp() -> None:
    assert level_from_bpp("hevc", 0.041) == 6
    assert level_from_bpp("hevc", 0.001) == 1 and level_from_bpp("hevc", 1.0) == 10
    assert level_from_bpp("h264", 0.074) == 6  # H.264 needs more bits for the same level
    assert level_from_bpp("mpeg2video", 0.148) == 6  # older codecs: about 2x H.264


def test_x265_sample_is_read() -> None:
    report = analyse(sample(audio=eac3()), X265)
    s = report.settings
    assert (s.codec, s.quality, s.ten_bit, s.max_height) == ("hevc", 8, True, None)
    assert report.sources["quality"] == "read" and report.sources["codec"] == "read"
    assert (s.audio, s.audio_codec, s.audio_kbps_per_channel) == ("convert", "eac3", 107)
    assert report.sources["audio"] == "read"
    assert "Quality read from its settings: CRF 20." in report.notes
    assert report.sample["encoder"] == "x265"


def test_x264_sample_keeps_h264_and_8_bit() -> None:
    report = analyse(sample("h264", bit_depth=8), X264)
    assert (report.settings.codec, report.settings.quality, report.settings.ten_bit) == (
        "h264",
        9,
        False,
    )


def test_gpu_sample_is_estimated_with_its_overhead() -> None:
    # 2.5 Mbit/s 1080p24 HEVC: 0.050 bits per pixel.
    plain = analyse(sample(), None)
    nvenc = analyse(sample(), None, "Lavc62.28.103 hevc_nvenc")
    assert plain.sources["quality"] == nvenc.sources["quality"] == "estimated"
    # The same bitrate means less quality from a GPU encoder: one level lower.
    assert (plain.settings.quality, nvenc.settings.quality) == (7, 6)
    qsv = analyse(sample(video_kbps=4000), None, "Lavc hevc_qsv")
    assert qsv.settings.quality < analyse(sample(video_kbps=4000), None).settings.quality
    assert any("NVENC" in n for n in nvenc.notes)


def test_abr_x265_falls_back_to_the_estimate() -> None:
    report = analyse(sample(), X265_ABR)
    assert report.sources["quality"] == "estimated"


def test_unknown_bitrate_uses_the_default() -> None:
    report = analyse(sample(video_kbps=None), None)
    assert report.settings.quality == 6 and report.sources["quality"] == "default"


def test_other_codecs_become_hevc() -> None:
    report = analyse(sample("mpeg2video", bit_depth=8, video_kbps=8000), None)
    assert report.settings.codec == "hevc" and report.sources["codec"] == "default"
    assert any("MPEG2VIDEO" in n for n in report.notes)


@pytest.mark.parametrize(
    "audio",
    [
        Stream(index=1, kind="audio", codec="truehd", channels=6, default=True),
        eac3(profile="Dolby Digital Plus + Dolby Atmos"),
        Stream(index=1, kind="audio", codec="dts", channels=6, bit_rate=1_509_000),
        eac3().model_copy(update={"bit_rate": None}),
    ],
)
def test_audio_that_is_copied(audio: Stream) -> None:
    report = analyse(sample(audio=audio), X265)
    assert report.settings.audio == "copy" and report.sources["audio"] == "default"


def test_aac_stereo_and_ac3() -> None:
    aac = Stream(index=1, kind="audio", codec="aac", channels=2, bit_rate=160_000)
    report = analyse(sample(audio=aac), X265)
    s = report.settings
    assert (s.audio, s.audio_codec, s.audio_kbps_per_channel) == ("convert", "aac", 80)
    ac3 = Stream(index=1, kind="audio", codec="ac3", channels=6, bit_rate=448_000)
    assert analyse(sample(audio=ac3), X265).settings.audio_codec == "eac3"


def test_no_video_is_refused() -> None:
    info = MediaInfo(container="x", duration_s=1, size_bytes=1, bit_rate=None, streams=[])
    with pytest.raises(ValueError, match="no video"):
        analyse(info, None)


@pytest.mark.skipif(FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed")
def test_real_x265_file(tmp_path: Path) -> None:
    path = make(tmp_path / "s.mkv", Spec(codec="libx265", audio=[Audio("eng", default=True)]))
    # make() uses x265's default CRF (28) at the ultrafast preset.
    info = probe(path)
    text = read_settings_string(FFMPEG or "ffmpeg", path, "hevc")
    report = analyse(info, text, read_encoder_tag(path))
    assert report.sources["quality"] == "read"
    assert report.settings.quality == 3  # CRF 28
    assert read_settings_string(FFMPEG or "ffmpeg", path, "av1") is None
