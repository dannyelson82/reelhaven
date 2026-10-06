import os
import stat
from pathlib import Path

import pytest

from reelhaven.media.probe import ProbeError, ffmpeg_input, probe
from tests.media_fixtures import FFMPEG, Audio, Spec, Sub, make

# Skipped only on machines without ffmpeg. CI installs it, so these tests
# can never silently disappear there.
pytestmark = pytest.mark.skipif(
    FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed"
)


def test_probe_multi_language_file(tmp_path: Path) -> None:
    path = make(
        tmp_path / "movie.mkv",
        Spec(
            audio=[
                Audio("eng", "English", default=True, channels=6),
                Audio("fre", "Français"),
                Audio("eng", "Commentary", comment=True),
            ],
            subs=[
                Sub("eng", "English"),
                Sub("eng", "English (Forced)", default=True, forced=True),
                Sub("eng", "SDH", hearing_impaired=True),
                Sub(None),
            ],
        ),
    )
    info = probe(path)
    assert info.duration_s == pytest.approx(1.0, abs=0.2)
    assert info.video is not None
    assert info.video.codec == "h264"
    audio = info.of_kind("audio")
    assert [a.language for a in audio] == ["eng", "fra", "eng"]
    assert audio[0].channels == 6
    assert audio[0].default and not audio[1].default
    assert audio[2].commentary
    subs = info.of_kind("subtitle")
    assert [s.forced for s in subs] == [False, True, False, False]
    assert subs[2].hearing_impaired
    assert subs[3].language is None  # untagged


def test_probe_hevc_mp4(tmp_path: Path) -> None:
    path = make(tmp_path / "clip.mp4", Spec(codec="libx265", subs=[Sub("eng")]))
    info = probe(path)
    assert "mp4" in info.container
    assert info.video is not None
    assert info.video.codec == "hevc"
    assert info.of_kind("subtitle")[0].codec == "mov_text"


@pytest.mark.parametrize(
    "name",
    [
        "-i.mkv",
        "--help.mkv",
        "name with spaces.mkv",
        'quote\'s "and" more.mkv',
        "$(touch pwned).mkv",
        "semi;colon && echo hacked.mkv",
        "http:evil.mkv",
        "pipe:1.mkv",
        "ünïcödé 日本.mkv",
    ],
)
def test_hostile_filenames_are_just_filenames(tmp_path: Path, name: str) -> None:
    path = make(tmp_path / name, Spec())
    info = probe(path)
    assert info.video is not None
    assert not (tmp_path / "pwned").exists()
    assert not (Path.cwd() / "pwned").exists()


def test_relative_paths_refused() -> None:
    with pytest.raises(ValueError, match="absolute"):
        ffmpeg_input(Path("movie.mkv"))


def test_not_a_media_file(tmp_path: Path) -> None:
    path = tmp_path / "notes.mkv"
    path.write_text("definitely not a video")
    with pytest.raises(ProbeError):
        probe(path)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ProbeError):
        probe(tmp_path / "gone.mkv")


def test_missing_ffprobe(tmp_path: Path) -> None:
    with pytest.raises(ProbeError, match="could not run"):
        probe(tmp_path / "x.mkv", ffprobe=str(tmp_path / "no-such-ffprobe"))


def test_timeout(tmp_path: Path) -> None:
    slow = tmp_path / "slow-ffprobe"
    slow.write_text("#!/bin/sh\nsleep 5\n")
    slow.chmod(slow.stat().st_mode | stat.S_IXUSR)
    if not os.access(slow, os.X_OK):
        pytest.skip("cannot execute scripts here")
    with pytest.raises(ProbeError, match="timed out"):
        probe(tmp_path / "x.mkv", ffprobe=str(slow), timeout=0.5)
