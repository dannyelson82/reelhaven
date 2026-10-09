"""Comparison clips (ADR-0031): near-lossless H.264 a browser can play, on the GPU."""

from pathlib import Path

from reelhaven.devices import CPU
from reelhaven.encoders import Device
from reelhaven.quality_metrics import clip_command

NVIDIA = Device(id="nvidia:1", kind="nvidia", name="RTX", family="nvenc", index=1)
INTEL = Device(
    id="intel:0", kind="intel", name="UHD", family="qsv", render_node="/dev/dri/renderD128"
)


def _command(device: Device, hdr: bool = False) -> list[str]:
    return clip_command(
        "ffmpeg", Path("/m/in.mkv"), 100, 15, Path("/t/clip.mp4"), (3840, 1600), hdr, device
    )


def _after(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


def test_clip_is_a_short_silent_h264_scene() -> None:
    args = _command(CPU)
    assert _after(args, "-ss") == "100.000" and _after(args, "-t") == "15.000"
    assert args.index("-ss") < args.index("-i")  # fast seek, same frame in both files
    assert {"-an", "-sn", "-dn"} <= set(args)
    assert _after(args, "-c:v") == "libx264" and _after(args, "-crf") == "12"
    assert _after(args, "-vf") == "scale=3840:1600:flags=lanczos,format=yuv420p"
    assert _after(args, "-movflags") == "+faststart"  # plays before it has fully loaded


def test_clip_on_the_gpu() -> None:
    nvidia = _command(NVIDIA)
    assert _after(nvidia, "-c:v") == "h264_nvenc" and _after(nvidia, "-qp") == "14"
    assert _after(nvidia, "-gpu") == "1"
    intel = _command(INTEL)
    assert _after(intel, "-c:v") == "h264_qsv"
    assert intel.index("-init_hw_device") < intel.index("-i")
    assert _after(intel, "-vf").endswith("format=nv12,hwupload=extra_hw_frames=64")


def test_hdr_clip_is_tone_mapped_first() -> None:
    assert _after(_command(CPU, hdr=True), "-vf").startswith("tonemapx=")
