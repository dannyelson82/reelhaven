"""The verifier's stream-layout check (ARCHITECTURE.md §6.7)."""

import subprocess
from pathlib import Path

import pytest

from reelhaven.jobs.verify import VerificationError, decode_errors, verify_output
from reelhaven.media.probe import probe
from tests.media_fixtures import FFMPEG, Audio, Spec, make

pytestmark = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not installed")


def retag(source: Path, output: Path, *metadata: str) -> Path:
    """A copy of ``source`` with changed stream tags (as a remux might produce)."""
    args = [FFMPEG or "ffmpeg", "-v", "error", "-i", str(source), "-map", "0", "-c", "copy"]
    for item in metadata:
        args += item.split(" ", 1)
    subprocess.run([*args, str(output)], check=True)  # noqa: S603 - argument list, no shell
    return output


def check(source: Path, output: Path) -> None:
    info = probe(source)
    expected: list[tuple[str, str | None, bool | None]] = [
        (s.kind, s.language, None) for s in info.streams
    ]
    verify_output(output, info, expected, FFMPEG or "ffmpeg", "ffprobe")


def test_video_language_tag_may_change(tmp_path: Path) -> None:
    source = make(tmp_path / "in.mkv", Spec(audio=[Audio("eng", default=True)]))
    assert probe(source).streams[0].language is None  # untagged video
    output = retag(source, tmp_path / "out.mkv", "-metadata:s:v:0 language=eng")
    assert probe(output).streams[0].language == "eng"
    check(source, output)  # no error


def test_audio_language_must_match(tmp_path: Path) -> None:
    source = make(tmp_path / "in.mkv", Spec(audio=[Audio("jpn", default=True)]))
    output = retag(source, tmp_path / "out.mkv", "-metadata:s:a:0 language=eng")
    with pytest.raises(VerificationError, match="stream 1: expected audio jpn, found audio eng"):
        check(source, output)


DTS = (
    "[null @ 0x558c775f4580] Application provided invalid, non monotonically increasing dts"
    " to muxer in stream 0: {n} >= {n}"
)


def test_decode_test_ignores_the_null_muxers_timestamp_complaints() -> None:
    """Seen on a real file: only the test's throwaway output complained (owner report)."""
    stderr = "\n".join(DTS.format(n=n) for n in (32, 36, 39, 42, 46)) + "\n"
    assert decode_errors(stderr) == ""


@pytest.mark.parametrize(
    "problem",
    [
        "[hevc @ 0x55d0c0a1b2c0] Could not find ref with POC 12",
        "[h264 @ 0x55d0c0a1b2c0] error while decoding MB 33 17, bytestream -5",
        "Error while decoding stream #0:0: Invalid data found when processing input",
        "[null @ 0x558c775f4580] Something else went wrong",
    ],
)
def test_decode_test_still_reports_real_errors(problem: str) -> None:
    stderr = f"{DTS.format(n=32)}\n{problem}\n{DTS.format(n=36)}\n"
    assert decode_errors(stderr) == problem
