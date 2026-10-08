from typing import Any

import pytest

from reelhaven.encode_planner import (
    encode_marker,
    expected_bitrate,
    format_size,
    plan_video,
    profile_fingerprint,
)
from reelhaven.media.info import HdrType, MediaInfo, Stream
from reelhaven.planner import plan_file
from reelhaven.policy import LanguagePolicy
from reelhaven.profiles import ProfileSettings

BALANCED = ProfileSettings()
GB = 1_000_000_000


def movie(
    codec: str = "h264",
    height: int = 1080,
    video_mbps: float = 10.0,
    hdr: HdrType = "sdr",
    duration: float = 7200.0,
    tags: dict[str, str] | None = None,
    **extra: Any,
) -> MediaInfo:
    width = {2160: 3840, 1080: 1920, 720: 1280}[height]
    video_bps = int(video_mbps * 1_000_000)
    audio_bps = 640_000
    size = int((video_bps + audio_bps) * duration / 8)
    return MediaInfo(
        container="matroska,webm",
        duration_s=duration,
        size_bytes=size,
        bit_rate=None,
        tags=tags or {},
        streams=[
            Stream(
                index=0,
                kind="video",
                codec=codec,
                width=width,
                height=height,
                frame_rate=23.976,
                hdr=hdr,
                bit_rate=video_bps,
                **extra,
            ),
            Stream(
                index=1,
                kind="audio",
                codec="ac3",
                language="eng",
                default=True,
                channels=6,
                bit_rate=audio_bps,
            ),
        ],
    )


def test_bitrate_model_is_sensible() -> None:
    hevc_1080 = expected_bitrate("hevc", 6, 1920, 1080, 23.976)
    assert 2_000_000 < hevc_1080 < 4_000_000  # roughly 2.7 Mb/s for balanced 1080p HEVC
    assert (
        expected_bitrate("av1", 6, 1920, 1080, 23.976)
        < hevc_1080
        < expected_bitrate("h264", 6, 1920, 1080, 23.976)
    )
    assert expected_bitrate("hevc", 8, 1920, 1080, 24) > hevc_1080


def test_big_h264_is_encoded() -> None:
    video = plan_video(movie(), BALANCED)
    assert video.decision == "encode"
    assert video.savings_percent is not None and video.savings_percent > 50
    assert video.bytes_after_estimate is not None and video.bytes_before is not None
    assert video.bytes_after_estimate < video.bytes_before


def test_already_efficient_hevc_is_kept() -> None:
    video = plan_video(movie(codec="hevc", video_mbps=2.5), BALANCED)
    assert (video.decision, video.reason) == ("keep", "Already HEVC at a low bitrate.")


def test_small_savings_are_skipped() -> None:
    # H.264 already close to the HEVC target: re-encoding wouldn't gain 10 %.
    video = plan_video(movie(video_mbps=2.9), BALANCED)
    assert video.decision == "keep"
    assert "below the 10 % minimum" in video.reason
    assert video.reason.startswith("Would save only about ")


def test_downscaling_counts_even_for_efficient_hevc() -> None:
    video = plan_video(
        movie(codec="hevc", height=2160, video_mbps=9), ProfileSettings(max_height=1080)
    )
    assert video.decision == "encode"
    assert (video.height_before, video.height_after) == (2160, 1080)


@pytest.mark.parametrize(
    ("hdr", "reason"),
    [
        ("dolby_vision", "Dolby Vision is skipped"),
        ("hdr10plus", "HDR10+ is skipped"),
    ],
)
def test_dynamic_hdr_is_never_encoded(hdr: HdrType, reason: str) -> None:
    video = plan_video(movie(codec="hevc", height=2160, video_mbps=60, hdr=hdr), BALANCED)
    assert video.decision == "keep"
    assert video.reason.startswith(reason)


def test_hdr10_is_encoded_in_10_bit_even_with_8_bit_profile() -> None:
    video = plan_video(
        movie(codec="hevc", height=2160, video_mbps=60, hdr="hdr10"), ProfileSettings(ten_bit=False)
    )
    assert video.decision == "encode"
    assert video.ten_bit is True


def test_hdr_to_h264_refused() -> None:
    assert (
        plan_video(movie(hdr="hlg", video_mbps=40), ProfileSettings(codec="h264")).decision
        == "keep"
    )


def test_already_encoded_with_same_profile() -> None:
    info = movie(tags={"reelhaven": encode_marker(BALANCED)})
    assert plan_video(info, BALANCED).reason == "Already encoded by ReelHaven with this profile."
    # A different profile makes the file eligible again.
    assert plan_video(info, ProfileSettings(quality=8)).decision == "encode"


def test_fingerprint_ignores_audio_settings() -> None:
    assert profile_fingerprint(BALANCED) == profile_fingerprint(
        ProfileSettings(audio="compress_lossless")
    )
    assert profile_fingerprint(BALANCED) != profile_fingerprint(ProfileSettings(quality=7))


def test_unknown_size_is_kept() -> None:
    info = movie().model_copy(update={"size_bytes": None})
    assert plan_video(info, BALANCED).decision == "keep"


def test_video_bitrate_estimated_from_file_size() -> None:
    info = movie()
    info.streams[0].bit_rate = None
    assert plan_video(info, BALANCED).decision == "encode"


def test_stale_stream_bitrate_bigger_than_the_file_is_not_trusted() -> None:
    """A leftover BPS tag claimed more than the whole file, so the estimate said 100 %."""
    info = movie(video_mbps=4.0)
    info.streams[0].bit_rate = 40_000_000  # ten times the real rate
    video = plan_video(info, BALANCED)
    honest = plan_video(movie(video_mbps=4.0), BALANCED)
    assert video.savings_percent is not None and video.savings_percent < 100
    assert video.savings_percent == pytest.approx(honest.savings_percent, abs=2)


def test_saving_is_described_as_a_size() -> None:
    video = plan_video(movie(), BALANCED)
    saved = (video.bytes_before or 0) - (video.bytes_after_estimate or 0)
    assert video.reason == f"Saves about {format_size(saved)} ({video.savings_percent:.0f} %)."
    assert video.reason.startswith("Saves about ") and " GB (" in video.reason


@pytest.mark.parametrize(
    ("n", "text"),
    [
        (0, "0 B"),
        (999, "999 B"),
        (1_000, "1.0 KB"),
        (120_400_000, "120 MB"),
        (3_240_000_000, "3.2 GB"),
    ],
)
def test_format_size(n: int, text: str) -> None:
    assert format_size(n) == text


# --- combined with the language plan -----------------------------------------------


def test_plan_file_without_profile_is_the_language_plan() -> None:
    p = plan_file(movie(), "eng", LanguagePolicy(), None)
    assert p.video is None and p.action == "skip"


def test_plan_file_encode_includes_track_changes() -> None:
    info = movie()
    info.streams.append(
        Stream(index=2, kind="audio", codec="ac3", language="fra", channels=6, bit_rate=640_000)
    )
    p = plan_file(info, "eng", LanguagePolicy(), BALANCED)
    assert p.action == "encode"
    assert p.details[0].startswith("Re-encode video to HEVC 10-bit")
    assert "Remove audio: French." in p.details
    assert p.summary.endswith("Will re-encode the video and apply the track changes.")


def test_wrong_language_file_is_not_encoded() -> None:
    info = movie()
    info.streams[1].language = "spa"
    p = plan_file(info, "eng", LanguagePolicy(), BALANCED)
    assert p.action == "skip"
    assert p.video is not None and p.video.decision == "keep"


def test_hdr10plus_flagged_but_language_changes_still_planned() -> None:
    info = movie(codec="hevc", height=2160, video_mbps=60, hdr="hdr10plus")
    info.streams.append(Stream(index=2, kind="audio", codec="ac3", language="deu", channels=6))
    p = plan_file(info, "eng", LanguagePolicy(), BALANCED)
    assert "hdr10plus" in p.flags
    assert p.action == "remux"


# --- audio conversion (ADR-0023) ------------------------------------------------------------

CONVERT_AAC = ProfileSettings(audio="convert", audio_codec="aac")


def with_audio(info: MediaInfo, codec: str, kbps: int | None, channels: int = 6) -> MediaInfo:
    info.streams[1] = Stream(
        index=1,
        kind="audio",
        codec=codec,
        language="eng",
        default=True,
        channels=channels,
        bit_rate=kbps * 1000 if kbps else None,
    )
    return info


def test_audio_only_plan_when_the_video_is_already_efficient() -> None:
    info = with_audio(movie(codec="hevc", video_mbps=2), "truehd", 4000)
    p = plan_file(info, "eng", LanguagePolicy(), CONVERT_AAC)
    assert p.video is not None and p.video.decision == "keep"
    assert p.action == "remux"
    (track,) = [t for t in p.tracks if t.convert_codec]
    assert (track.index, track.convert_codec, track.convert_kbps) == (1, "aac", 384)
    assert p.audio_saved_bytes == int((4_000_000 - 384_000) * 7200 / 8)
    assert p.remux_saved_bytes == p.audio_saved_bytes
    assert "Convert audio: English (TRUEHD) → AAC 384 kbit/s." in p.details
    assert p.summary == "Original language: English. Will convert 1 audio track."


def test_lossless_bitrate_is_estimated_when_unknown() -> None:
    info = with_audio(movie(codec="hevc", video_mbps=2), "truehd", None)
    p = plan_file(info, "eng", LanguagePolicy(), CONVERT_AAC)
    assert p.action == "remux"
    assert p.audio_saved_bytes and p.audio_saved_bytes > 0


def test_small_audio_savings_alone_are_skipped() -> None:
    # 1 Mbit/s E-AC-3 -> 384k AAC saves ~0.6 Mbit/s of a ~9 Mbit/s file: under 10 %.
    info = with_audio(movie(codec="hevc", height=2160, video_mbps=8), "eac3", 1000)
    p = plan_file(info, "eng", LanguagePolicy(), CONVERT_AAC)
    assert p.action == "skip"
    assert not any(t.convert_codec for t in p.tracks)
    assert p.audio_saved_bytes is None


def test_track_changes_take_the_audio_conversion_along() -> None:
    info = with_audio(movie(codec="hevc", height=2160, video_mbps=8), "eac3", 1000)
    info.streams.append(
        Stream(index=2, kind="audio", codec="ac3", language="fra", channels=6, bit_rate=448_000)
    )
    p = plan_file(info, "eng", LanguagePolicy(), CONVERT_AAC)
    assert p.action == "remux"
    assert [t.index for t in p.tracks if t.convert_codec] == [1]
    assert p.summary == (
        "Original language: English. Will remove 1 audio track, convert 1 audio track."
    )


def test_encode_counts_converted_audio_in_the_estimate() -> None:
    plain = plan_file(with_audio(movie(), "truehd", 4000), "eng", LanguagePolicy(), BALANCED)
    converted = plan_file(with_audio(movie(), "truehd", 4000), "eng", LanguagePolicy(), CONVERT_AAC)
    assert plain.action == converted.action == "encode"
    assert plain.video and converted.video
    assert converted.video.savings_percent > plain.video.savings_percent  # type: ignore[operator]
    assert converted.audio_saved_bytes
    assert any(d.startswith("Convert audio:") for d in converted.details)
    # The description follows the combined estimate, not the video-only one.
    assert converted.video.reason != plain.video.reason
    assert f"({converted.video.savings_percent:.0f} %)" in converted.video.reason


def test_copy_profile_and_review_files_convert_nothing() -> None:
    info = with_audio(movie(codec="hevc", video_mbps=2), "truehd", 4000)
    assert plan_file(info, "eng", LanguagePolicy(), BALANCED).action == "skip"
    info.streams[1].language = "spa"  # wrong language: needs review
    p = plan_file(info, "eng", LanguagePolicy(), CONVERT_AAC)
    assert p.action == "skip" and not any(t.convert_codec for t in p.tracks)


def test_downmix_is_planned_and_described() -> None:
    profile = ProfileSettings(audio="convert", audio_codec="aac", downmix_stereo=True)
    info = with_audio(movie(codec="hevc", video_mbps=2), "truehd", 4000)
    p = plan_file(info, "eng", LanguagePolicy(), profile)
    (track,) = [t for t in p.tracks if t.convert_codec]
    assert (track.convert_kbps, track.convert_channels) == (128, 2)
    assert "Convert audio: English (TRUEHD) → AAC stereo 128 kbit/s." in p.details
