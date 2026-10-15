"""Track changes on Dolby Vision files use the standard ffmpeg (ADR-0034)."""

from pathlib import Path

from reelhaven.config import Settings
from reelhaven.jobs.pipeline import remux_ffmpeg
from reelhaven.media.info import MediaInfo, Stream


def media(hdr: str) -> MediaInfo:
    video = Stream(index=0, kind="video", codec="hevc", hdr=hdr)  # type: ignore[arg-type]
    return MediaInfo(container="matroska", duration_s=1, size_bytes=1, bit_rate=1, streams=[video])


def test_dolby_vision_track_changes_use_the_copy_ffmpeg(tmp_path: Path) -> None:
    settings = Settings(
        config_dir=tmp_path, ffmpeg="jf-ffmpeg", copy_ffmpeg="/opt/ffmpeg-copy/ffmpeg"
    )
    assert remux_ffmpeg(settings, media("dolby_vision")) == "/opt/ffmpeg-copy/ffmpeg"
    assert remux_ffmpeg(settings, media("hdr10")) == "jf-ffmpeg"
    assert remux_ffmpeg(settings, media("sdr")) == "jf-ffmpeg"


def test_without_a_copy_ffmpeg_everything_uses_ffmpeg(tmp_path: Path) -> None:
    settings = Settings(config_dir=tmp_path, ffmpeg="jf-ffmpeg")
    assert remux_ffmpeg(settings, media("dolby_vision")) == "jf-ffmpeg"
