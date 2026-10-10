"""Objective quality of an encode compared with its source (ADR-0020).

XPSNR (perceptually weighted PSNR, ffmpeg 7+) and SSIM, measured on a few
short segments. jellyfin-ffmpeg has no VMAF. Ratings are guidance; the
owner judges the still frames too.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from reelhaven.cpu_limit import preexec
from reelhaven.devices import CPU as CPU_DEVICE
from reelhaven.encoders import (
    Device,
    Family,
    device_select_args,
    encoder_name,
    hw_init_args,
    profile_args,
    upload_filters,
)
from reelhaven.media.probe import ffmpeg_input

SEGMENT_SECONDS = 10.0
_XPSNR = re.compile(r"XPSNR\s+y:\s*([0-9.]+|inf)")
_SSIM = re.compile(r"SSIM .*All:([0-9.]+)")


@dataclass
class Quality:
    xpsnr: float | None  # luma XPSNR in dB, average over segments
    ssim: float | None  # 0..1
    rating: str


def rate(xpsnr: float | None, ssim: float | None) -> str:
    if xpsnr is not None:
        if xpsnr >= 40:
            return "Indistinguishable"
        if xpsnr >= 36:
            return "Very good"
        if xpsnr >= 33:
            return "Good"
        return "Visible loss"
    if ssim is not None:
        if ssim >= 0.985:
            return "Indistinguishable"
        if ssim >= 0.97:
            return "Very good"
        if ssim >= 0.95:
            return "Good"
        return "Visible loss"
    return "Unknown"


def segment_starts(duration: float, count: int = 3) -> list[float]:
    if duration <= SEGMENT_SECONDS * 1.5:
        return [0.0]
    span = duration - SEGMENT_SECONDS
    return [round(span * (i + 1) / (count + 1), 3) for i in range(count)]


def _compare(
    ffmpeg: str,
    source: Path,
    encoded: Path,
    start: float,
    metric: str,
    width: int,
    height: int,
    timeout: float,
) -> str:
    # Both sides scaled to the encoded size and same pixel format before comparing.
    graph = (
        f"[0:v]scale={width}:{height}:flags=bicubic,format=yuv420p10le,setpts=PTS-STARTPTS[dist];"
        f"[1:v]scale={width}:{height}:flags=bicubic,format=yuv420p10le,setpts=PTS-STARTPTS[ref];"
        f"[dist][ref]{metric}"
    )
    args = [
        ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "info",
        "-ss", f"{start:.3f}", "-t", str(SEGMENT_SECONDS), "-i", ffmpeg_input(encoded),
        "-ss", f"{start:.3f}", "-t", str(SEGMENT_SECONDS), "-i", ffmpeg_input(source),
        "-lavfi", graph, "-an", "-sn", "-f", "null", "-",
    ]  # fmt: skip
    result = subprocess.run(  # noqa: S603 - argument list, no shell
        args, capture_output=True, timeout=timeout, check=False, preexec_fn=preexec()
    )
    return result.stderr.decode("utf-8", "replace")


def has_xpsnr(ffmpeg: str) -> bool:
    result = subprocess.run(  # noqa: S603 - argument list, no shell
        [ffmpeg, "-hide_banner", "-filters"],
        capture_output=True,
        timeout=30,
        check=False,
        preexec_fn=preexec(),
    )
    return b" xpsnr " in result.stdout


def measure(
    ffmpeg: str,
    source: Path,
    encoded: Path,
    duration: float,
    width: int,
    height: int,
    timeout: float = 900,
) -> Quality:
    xpsnr_values: list[float] = []
    ssim_values: list[float] = []
    use_xpsnr = has_xpsnr(ffmpeg)
    for start in segment_starts(duration):
        if use_xpsnr:
            found = _XPSNR.findall(
                _compare(ffmpeg, source, encoded, start, "xpsnr", width, height, timeout)
            )
            if found and found[-1] != "inf":
                xpsnr_values.append(float(found[-1]))
            elif found:
                xpsnr_values.append(99.0)  # identical frames
        found = _SSIM.findall(
            _compare(ffmpeg, source, encoded, start, "ssim", width, height, timeout)
        )
        if found:
            ssim_values.append(float(found[-1]))
    xpsnr = round(sum(xpsnr_values) / len(xpsnr_values), 2) if xpsnr_values else None
    ssim = round(sum(ssim_values) / len(ssim_values), 4) if ssim_values else None
    return Quality(xpsnr=xpsnr, ssim=ssim, rating=rate(xpsnr, ssim))


# HDR stills are tone-mapped for display, the same way on both sides, so they compare
# fairly on an ordinary screen.
_TONEMAP = "tonemapx=tonemap=bt2390:transfer=bt709:matrix=bt709:primaries=bt709:range=tv"


def extract_frame(
    ffmpeg: str,
    video: Path,
    at: float,
    output: Path,
    size: tuple[int, int],
    hdr: bool = False,
    timeout: float = 120,
) -> None:
    """One lossless WebP still at ``at`` seconds, at exactly ``size`` (width, height).

    Lossless and full size, so zooming in shows the encode, not a JPEG's own blur; the new
    file is scaled to the original's size so both line up pixel for pixel."""
    filters = [f"scale={size[0]}:{size[1]}:flags=lanczos"]
    if hdr:
        filters.insert(0, _TONEMAP)
    args = [
        ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", f"{at:.3f}",
        "-i", ffmpeg_input(video), "-frames:v", "1", "-vf", ",".join(filters),
        "-c:v", "libwebp", "-lossless", "1", "-compression_level", "4", "-y",
        ffmpeg_input(output),
    ]  # fmt: skip
    subprocess.run(args, capture_output=True, timeout=timeout, check=True, preexec_fn=preexec())  # noqa: S603


# Near-lossless H.264 per encoder family: far finer than the differences being judged.
_CLIP_QUALITY: dict[Family, list[str]] = {
    "nvenc": ["-preset", "p4", "-rc", "constqp", "-qp", "14"],
    "qsv": ["-preset", "medium", "-global_quality", "14"],
    "vaapi": ["-rc_mode", "CQP", "-qp", "14"],
    "cpu": ["-preset", "veryfast", "-crf", "12"],
}


def clip_command(
    ffmpeg: str,
    video: Path,
    start: float,
    seconds: float,
    output: Path,
    size: tuple[int, int],
    hdr: bool,
    device: Device,
) -> list[str]:
    """ffmpeg arguments for a comparison clip a browser can play (ADR-0031): ``seconds``
    from ``start``, at exactly ``size``, as near-lossless 8-bit H.264 in MP4, without sound.
    Encoded on ``device`` (a GPU where there is one); the picture is prepared on the CPU."""
    filters = [f"scale={size[0]}:{size[1]}:flags=lanczos", *upload_filters(device, False)]
    if hdr:
        filters.insert(0, _TONEMAP)
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", *hw_init_args(device),
        "-ss", f"{start:.3f}", "-i", ffmpeg_input(video), "-t", f"{seconds:.3f}",
        "-map", "0:v:0", "-an", "-sn", "-dn", "-vf", ",".join(filters),
        "-c:v", encoder_name(device, "h264"), *_CLIP_QUALITY[device.family],
        *device_select_args(device), *profile_args(device, "h264", False),
        "-movflags", "+faststart", "-y", ffmpeg_input(output),
    ]  # fmt: skip


def extract_clip(
    ffmpeg: str,
    video: Path,
    start: float,
    seconds: float,
    output: Path,
    size: tuple[int, int],
    hdr: bool = False,
    device: Device = CPU_DEVICE,
    timeout: float = 600,
) -> None:
    """Make a comparison clip on ``device``, falling back to the CPU if the GPU can't."""
    devices = [device] if device.family == "cpu" else [device, CPU_DEVICE]
    for index, attempt in enumerate(devices):
        args = clip_command(ffmpeg, video, start, seconds, output, size, hdr, attempt)
        try:
            subprocess.run(  # noqa: S603 - argument list, no shell
                args, capture_output=True, timeout=timeout, check=True, preexec_fn=preexec()
            )
            return
        except subprocess.CalledProcessError:
            if index == len(devices) - 1:
                raise
