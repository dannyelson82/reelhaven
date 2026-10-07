import os
from pathlib import Path

import pytest

from reelhaven.devices import CPU
from reelhaven.encode_planner import encode_marker
from reelhaven.encoders import Device
from reelhaven.jobs.encode_commands import (
    encode_command,
    expected_encode_layout,
    expected_video,
    is_lossless,
    output_streams,
    target_height,
)
from reelhaven.jobs.runner import run_ffmpeg
from reelhaven.jobs.verify import verify_output
from reelhaven.media.info import MediaInfo, Stream
from reelhaven.media.probe import probe
from reelhaven.planner import plan
from reelhaven.policy import LanguagePolicy
from reelhaven.profiles import ProfileSettings
from reelhaven.quality import quality_value
from tests.media_fixtures import FFMPEG, Audio, Spec, Sub, make

NVIDIA = Device(id="nvidia:1", kind="nvidia", name="RTX", family="nvenc", index=1)
INTEL = Device(
    id="intel:0000:00:02.0",
    kind="intel",
    name="Intel",
    family="qsv",
    render_node="/dev/dri/renderD128",
)
AMD = Device(
    id="amd:0000:03:00.0",
    kind="amd",
    name="AMD",
    family="vaapi",
    render_node="/dev/dri/renderD129",
)


# --- quality mapping -------------------------------------------------------------------


@pytest.mark.parametrize("family", ["cpu", "nvenc", "qsv", "vaapi"])
@pytest.mark.parametrize("codec", ["hevc", "av1", "h264"])
def test_quality_is_monotonic(family: str, codec: str) -> None:
    values = [quality_value(family, codec, level) for level in range(1, 11)]  # type: ignore[arg-type]
    assert values == sorted(values, reverse=True)  # better quality = lower value
    assert len(set(values)) >= 8


def test_quality_examples() -> None:
    assert quality_value("cpu", "hevc", 6) == 24
    assert quality_value("nvenc", "hevc", 6) == 29  # calibrated: same XPSNR as x265 -crf 24
    assert quality_value("qsv", "hevc", 6) == 21
    assert quality_value("vaapi", "hevc", 6) == 24  # AMD: not calibrated yet
    assert quality_value("cpu", "av1", 6) == 34
    with pytest.raises(ValueError):
        quality_value("cpu", "hevc", 0)


# --- stream layout -----------------------------------------------------------------------


def test_lossless_detection() -> None:
    def a(codec: str, profile: str | None = None, title: str | None = None) -> Stream:
        return Stream(index=1, kind="audio", codec=codec, profile=profile, title=title)

    assert is_lossless(a("truehd"))
    assert not is_lossless(a("truehd", "Dolby TrueHD + Dolby Atmos"))
    assert is_lossless(a("dts", "DTS-HD MA"))
    assert not is_lossless(a("dts", "DTS-HD MA + DTS:X"))
    assert not is_lossless(a("dts", "DTS"))
    assert is_lossless(a("flac")) and is_lossless(a("pcm_s24le"))
    assert not is_lossless(a("eac3", title="Atmos")) and not is_lossless(a("ac3"))


def media(**video: object) -> MediaInfo:
    return MediaInfo(
        container="matroska,webm",
        duration_s=100.0,
        size_bytes=10**9,
        bit_rate=None,
        streams=[
            Stream(index=0, kind="video", codec="hevc", width=3840, height=2160, **video),  # type: ignore[arg-type]
            Stream(
                index=1,
                kind="audio",
                codec="truehd",
                language="eng",
                channels=6,
                default=True,
                dispositions=["default"],
            ),
            Stream(
                index=2,
                kind="audio",
                codec="truehd",
                profile="Dolby TrueHD + Dolby Atmos",
                language="eng",
                channels=8,
            ),
            Stream(index=3, kind="audio", codec="ac3", language="fra", channels=6),
            Stream(
                index=4,
                kind="subtitle",
                codec="subrip",
                language="eng",
                forced=True,
                dispositions=["forced"],
            ),
            Stream(index=5, kind="attachment", codec="ttf"),
        ],
    )


def test_output_streams_and_stereo_track() -> None:
    info = media(hdr="hdr10")
    p = plan(info, "eng", LanguagePolicy())
    profile = ProfileSettings(audio="compress_lossless", add_stereo_aac=True)
    layout = output_streams(info, p, profile, "matroska")
    assert [(s.kind, s.source_index, s.action) for s in layout] == [
        ("video", 0, "encode-video"),
        ("audio", 1, "eac3"),  # lossless 5.1 compressed
        ("audio", 2, "copy"),  # Atmos always copied
        ("audio", 1, "aac-stereo"),  # added after the audio tracks
        ("subtitle", 4, "copy"),
        ("attachment", 5, "copy"),
    ]


def test_never_upscales() -> None:
    assert (
        target_height(Stream(index=0, kind="video", height=2160), ProfileSettings(max_height=1080))
        == 1080
    )
    assert (
        target_height(Stream(index=0, kind="video", height=720), ProfileSettings(max_height=1080))
        is None
    )
    assert target_height(Stream(index=0, kind="video", height=2160), ProfileSettings()) is None


# --- golden commands ------------------------------------------------------------------


def test_nvenc_hdr_4k_to_1080p_golden() -> None:
    info = media(hdr="hdr10")
    p = plan(info, "eng", LanguagePolicy())
    profile = ProfileSettings(max_height=1080, ten_bit=False, audio="compress_lossless")
    args = encode_command("ffmpeg", NVIDIA, Path("/m/a.mkv"), Path("/w/a.mkv"), info, p, profile)
    assert args == [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-nostats",
        "-i",
        "file:/m/a.mkv",
        "-map",
        "0:0",
        "-map",
        "0:1",
        "-map",
        "0:2",
        "-map",
        "0:4",
        "-map",
        "0:5",
        "-map_metadata",
        "0",
        "-map_chapters",
        "0",
        "-c",
        "copy",
        "-max_muxing_queue_size",
        "4096",
        # HDR forces 10-bit even though the profile says 8-bit
        "-filter:v:0",
        "scale=-2:1080:flags=lanczos,format=p010le",
        "-c:v:0",
        "hevc_nvenc",
        "-gpu",
        "1",
        "-profile:v",
        "main10",
        "-preset",
        "p5",
        "-tune",
        "hq",
        "-rc",
        "vbr",
        "-cq",
        "29",
        "-b:v",
        "0",
        "-spatial_aq",
        "1",
        "-rc-lookahead",
        "20",
        "-metadata:s:0",
        "BPS=",
        "-metadata:s:0",
        "NUMBER_OF_BYTES=",
        "-metadata:s:0",
        "NUMBER_OF_FRAMES=",
        "-metadata:s:0",
        "DURATION=",
        "-metadata:s:0",
        "_STATISTICS_TAGS=",
        "-c:a:0",
        "eac3",
        "-b:a:0",
        "640k",
        "-disposition:1",
        "default",
        "-disposition:2",
        "0",
        "-disposition:3",
        "default+forced",
        "-metadata",
        f"REELHAVEN={encode_marker(profile)}",
        "-f",
        "matroska",
        "file:/w/a.mkv",
    ]


def test_qsv_and_vaapi_commands() -> None:
    info = media()
    p = plan(info, "eng", LanguagePolicy())
    qsv = encode_command(
        "ffmpeg", INTEL, Path("/m/a.mkv"), Path("/w/a.mkv"), info, p, ProfileSettings()
    )
    assert qsv[8:14] == [
        "-init_hw_device",
        "vaapi=va:/dev/dri/renderD128",
        "-init_hw_device",
        "qsv=hw@va",
        "-filter_hw_device",
        "hw",
    ]
    assert "format=p010le,hwupload=extra_hw_frames=64" in qsv
    assert qsv[qsv.index("-preset") : qsv.index("-preset") + 4] == [
        "-preset",
        "medium",
        "-global_quality",
        "21",
    ]
    vaapi = encode_command(
        "ffmpeg", AMD, Path("/m/a.mkv"), Path("/w/a.mkv"), info, p, ProfileSettings(codec="av1")
    )
    assert "av1_vaapi" in vaapi and vaapi[
        vaapi.index("-rc_mode") : vaapi.index("-rc_mode") + 4
    ] == ["-rc_mode", "CQP", "-qp", "34"]


def test_hevc_in_mp4_gets_hvc1_tag() -> None:
    info = media().model_copy(update={"container": "mov,mp4"})
    p = plan(info, "eng", LanguagePolicy())
    args = encode_command(
        "ffmpeg", CPU, Path("/m/a.mp4"), Path("/w/a.mp4"), info, p, ProfileSettings()
    )
    assert args[args.index("-tag:v:0") : args.index("-tag:v:0") + 2] == ["-tag:v:0", "hvc1"]
    assert "+faststart+use_metadata_tags" in args


def test_hdr_in_h264_refused() -> None:
    info = media(hdr="hdr10")
    with pytest.raises(ValueError, match="HDR"):
        encode_command(
            "ffmpeg",
            CPU,
            Path("/m/a.mkv"),
            Path("/w/a.mkv"),
            info,
            plan(info, "eng", LanguagePolicy()),
            ProfileSettings(codec="h264"),
        )


# --- real CPU encodes -----------------------------------------------------------------

needs_ffmpeg = pytest.mark.skipif(
    FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed"
)


def encode_and_verify(
    tmp_path: Path, spec: Spec, profile: ProfileSettings, name: str = "in.mkv"
) -> MediaInfo:
    source = make(tmp_path / name, spec)
    info = probe(source)
    p = plan(info, "eng", LanguagePolicy())
    output = tmp_path / "out" / name
    output.parent.mkdir()
    run_ffmpeg(
        encode_command(FFMPEG or "ffmpeg", CPU, source, output, info, p, profile),
        info.duration_s,
        timeout_s=300,
    )
    return verify_output(
        output,
        info,
        expected_encode_layout(source, info, p, profile),
        FFMPEG or "ffmpeg",
        "ffprobe",
        expected_video=expected_video(info, profile),
    )


@needs_ffmpeg
def test_x265_encode_with_downscale_and_stereo(tmp_path: Path) -> None:
    spec = Spec(
        audio=[Audio("eng", default=True, channels=6), Audio("fre")],
        subs=[Sub("eng")],
        size="1920x1080",
        seconds=2,
    )
    result = encode_and_verify(
        tmp_path,
        spec,
        ProfileSettings(quality=4, speed="fast", max_height=720, add_stereo_aac=True),
    )
    assert result.video is not None
    assert (result.video.codec, result.video.height, result.video.bit_depth) == ("hevc", 720, 10)
    audio = result.of_kind("audio")
    assert [(a.language, a.channels) for a in audio] == [("eng", 6), ("eng", 2)]
    assert audio[1].title == "Stereo (AAC)"


@needs_ffmpeg
def test_svt_av1_encode(tmp_path: Path) -> None:
    result = encode_and_verify(
        tmp_path, Spec(seconds=2, size="640x360"), ProfileSettings(codec="av1", speed="fast")
    )
    assert result.video is not None and result.video.codec == "av1"


@needs_ffmpeg
def test_hdr10_survives_reencode(tmp_path: Path) -> None:
    spec = Spec(hdr10=True, size="640x360", seconds=2)
    result = encode_and_verify(tmp_path, spec, ProfileSettings(ten_bit=False, speed="fast"))
    assert result.video is not None
    assert result.video.hdr == "hdr10"
    assert result.video.bit_depth == 10


@needs_ffmpeg
def test_mp4_encode(tmp_path: Path) -> None:
    result = encode_and_verify(
        tmp_path,
        Spec(seconds=2, size="640x360", subs=[Sub("eng")]),
        ProfileSettings(speed="fast"),
        name="in.mp4",
    )
    assert result.video is not None and result.video.codec == "hevc"
