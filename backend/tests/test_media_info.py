from typing import Any

from reelhaven.media.info import parse


def stream(**kwargs: Any) -> dict[str, Any]:
    return {"index": 0, "codec_type": "video", "codec_name": "hevc", **kwargs}


def probe(*streams: dict[str, Any], **fmt: Any) -> dict[str, Any]:
    return {
        "streams": list(streams),
        "format": {"format_name": "matroska,webm", "duration": "10.5", "size": "1000", **fmt},
    }


def test_basic_fields() -> None:
    info = parse(
        probe(
            stream(width=1920, height=1080, pix_fmt="yuv420p10le", avg_frame_rate="24000/1001"),
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "eac3",
                "channels": 6,
                "channel_layout": "5.1(side)",
                "sample_rate": "48000",
                "tags": {"LANGUAGE": "fre", "title": "Français"},
                "disposition": {"default": 1},
            },
            bit_rate="5000000",
        )
    )
    assert info.container == "matroska,webm"
    assert info.duration_s == 10.5
    assert info.bit_rate == 5_000_000
    video, audio = info.streams
    assert (video.width, video.height, video.bit_depth, video.frame_rate) == (
        1920,
        1080,
        10,
        23.976,
    )
    assert video.hdr == "sdr"
    assert audio.language == "fra"
    assert audio.raw_language == "fre"
    assert audio.default is True
    assert (audio.channels, audio.sample_rate) == (6, 48000)


def test_hdr_detection() -> None:
    assert parse(probe(stream(color_transfer="smpte2084"))).streams[0].hdr == "hdr10"
    assert parse(probe(stream(color_transfer="arib-std-b67"))).streams[0].hdr == "hlg"
    dv = stream(
        color_transfer="smpte2084",
        side_data_list=[{"side_data_type": "DOVI configuration record"}],
    )
    assert parse(probe(dv)).streams[0].hdr == "dolby_vision"
    hdr10plus = parse(
        probe(stream(color_transfer="smpte2084")),
        [{"side_data_type": "HDR Dynamic Metadata SMPTE2094-40 (HDR10+)"}],
    )
    assert hdr10plus.streams[0].hdr == "hdr10plus"


def test_flags_from_titles() -> None:
    def sub(title: str, **disposition: int) -> dict[str, Any]:
        return {
            "index": 1,
            "codec_type": "subtitle",
            "codec_name": "subrip",
            "tags": {"title": title},
            "disposition": disposition,
        }

    assert parse(probe(sub("English (Forced)"))).streams[0].forced
    assert parse(probe(sub("Signs", forced=1))).streams[0].forced
    assert not parse(probe(sub("Enforcement Squad"))).streams[0].forced
    assert parse(probe(sub("English SDH"))).streams[0].hearing_impaired
    assert parse(probe(sub("Director's Commentary"))).streams[0].commentary


def test_image_subtitles_and_cover_art() -> None:
    info = parse(
        probe(
            stream(codec_name="mjpeg", disposition={"attached_pic": 1}),
            stream(index=1, codec_name="h264"),
            {"index": 2, "codec_type": "subtitle", "codec_name": "hdmv_pgs_subtitle"},
            {"index": 3, "codec_type": "attachment", "codec_name": "ttf"},
        )
    )
    assert info.video is not None
    assert info.video.codec == "h264"
    assert info.streams[2].image_based is True
    assert info.streams[3].kind == "attachment"


def test_missing_fields_are_tolerated() -> None:
    info = parse({"streams": [{"codec_type": "audio"}], "format": {}})
    assert info.container == "unknown"
    assert info.duration_s is None
    assert info.streams[0].language is None
