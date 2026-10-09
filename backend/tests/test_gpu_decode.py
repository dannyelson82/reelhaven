"""Decoding on the GPU, with CPU decoding as the fallback (ADR-0029)."""

from collections.abc import Callable
from pathlib import Path

import pytest

from reelhaven.devices import CPU
from reelhaven.encoders import gpu_decodes
from reelhaven.jobs import encode_run
from reelhaven.jobs.encode_commands import encode_command
from reelhaven.jobs.runner import CancelledError, RunError
from reelhaven.planner import plan
from reelhaven.policy import LanguagePolicy
from reelhaven.profiles import ProfileSettings
from tests.test_encode_commands import INTEL, NVIDIA, media


@pytest.mark.parametrize(
    ("codec", "bit_depth", "pix_fmt", "expected"),
    [
        ("h264", 8, "yuv420p", True),
        ("h264", None, None, True),  # scanned before pix_fmt was recorded: assume 4:2:0
        ("h264", 10, "yuv420p10le", False),  # Hi10P: NVDEC can't
        ("h264", 8, "yuv422p", False),
        ("hevc", 10, "yuv420p10le", True),
        ("hevc", 12, "yuv420p12le", True),
        ("hevc", 10, "yuv444p10le", False),
        ("av1", 10, "yuv420p10le", True),
        ("vp9", 8, "yuv420p", True),
        ("mpeg2video", 8, "yuv420p", True),
        ("vc1", 8, "yuv420p", True),
        ("mpeg4", 8, "yuv420p", False),  # Xvid/DivX: CPU
        (None, 8, None, False),
    ],
)
def test_nvenc_decodes_what_nvdec_can(
    codec: str | None, bit_depth: int | None, pix_fmt: str | None, expected: bool
) -> None:
    assert gpu_decodes(NVIDIA, codec, bit_depth, pix_fmt) is expected


def test_other_devices_keep_cpu_decoding_for_now() -> None:
    assert not gpu_decodes(INTEL, "h264", 8, "yuv420p")
    assert not gpu_decodes(CPU, "h264", 8, "yuv420p")


def _command(gpu_decode: bool, **profile: object) -> list[str]:
    info = media(hdr="hdr10")
    p = plan(info, "eng", LanguagePolicy())
    settings = ProfileSettings(**profile)  # type: ignore[arg-type]
    return encode_command(
        "ffmpeg", NVIDIA, Path("/m/a.mkv"), Path("/w/a.mkv"), info, p, settings, gpu_decode
    )


def test_gpu_decode_command_keeps_frames_on_the_gpu() -> None:
    args = _command(True, max_height=1080)
    before_input = args[: args.index("-i")]
    assert before_input[-6:] == [
        "-hwaccel",
        "cuda",
        "-hwaccel_device",
        "1",  # the same card that encodes
        "-hwaccel_output_format",
        "cuda",
    ]
    vf = args[args.index("-filter:v:0") + 1]
    assert vf == "scale_cuda=w=-2:h=1080:interp_algo=lanczos:format=p010le"
    # Everything after the video filter is the same as with CPU decoding.
    cpu = _command(False, max_height=1080)
    assert args[args.index("-c:v:0") :] == cpu[cpu.index("-c:v:0") :]


def test_gpu_decode_without_scaling_only_sets_the_bit_depth() -> None:
    args = _command(True)
    assert args[args.index("-filter:v:0") + 1] == "scale_cuda=format=p010le"


# --- the fallback ---------------------------------------------------------------------------


def _run(
    monkeypatch: pytest.MonkeyPatch, outcomes: list[Exception | None], **video: object
) -> tuple[list[list[str]], Callable[[], bool]]:
    """run_encode with ffmpeg replaced: each call takes the next outcome."""
    calls: list[list[str]] = []

    def fake(args: list[str], *_a: object, **_k: object) -> None:
        calls.append(args)
        outcome = outcomes.pop(0)
        if outcome is not None:
            raise outcome

    monkeypatch.setattr(encode_run, "run_ffmpeg", fake)
    info = media(**video)
    p = plan(info, "eng", LanguagePolicy())

    def go() -> bool:
        return encode_run.run_encode(
            "ffmpeg", NVIDIA, Path("/m/a.mkv"), Path("/nonexistent/a.mkv"), info, p,
            ProfileSettings(), timeout_s=60, on_progress=lambda *_: None,
            should_cancel=lambda: False,
        )  # fmt: skip

    return calls, go


def test_gpu_decoding_is_used_when_it_works(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, go = _run(monkeypatch, [None], bit_depth=10, pix_fmt="yuv420p10le")
    assert go() is True
    assert len(calls) == 1 and "-hwaccel" in calls[0]


def test_failed_gpu_decoding_is_retried_on_the_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, go = _run(monkeypatch, [RunError("hwaccel init failed"), None], bit_depth=10)
    assert go() is False
    assert ["-hwaccel" in c for c in calls] == [True, False]


def test_cpu_failure_after_the_retry_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, go = _run(monkeypatch, [RunError("gpu"), RunError("cpu too")], bit_depth=10)
    with pytest.raises(RunError, match="cpu too"):
        go()
    assert len(calls) == 2


def test_cancelling_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, go = _run(monkeypatch, [CancelledError()], bit_depth=10)
    with pytest.raises(CancelledError):
        go()
    assert len(calls) == 1


def test_formats_the_card_cant_decode_go_straight_to_the_cpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls, go = _run(monkeypatch, [None], bit_depth=10, pix_fmt="yuv422p10le")
    assert go() is False
    assert len(calls) == 1 and "-hwaccel" not in calls[0]


def test_the_decoder_is_reported_for_each_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes: list[Exception | None] = [RunError("gpu"), None]

    def fake(_args: list[str], *_a: object, **_k: object) -> None:
        outcome = outcomes.pop(0)
        if outcome is not None:
            raise outcome

    monkeypatch.setattr(encode_run, "run_ffmpeg", fake)
    info = media(bit_depth=10)
    decoders: list[str] = []
    encode_run.run_encode(
        "ffmpeg", NVIDIA, Path("/m/a.mkv"), Path("/nonexistent/a.mkv"), info,
        plan(info, "eng", LanguagePolicy()), ProfileSettings(), timeout_s=60,
        on_progress=lambda *_: None, should_cancel=lambda: False, on_decoder=decoders.append,
    )  # fmt: skip
    assert decoders == ["gpu", "cpu"]  # the job's record ends on what really decoded it
