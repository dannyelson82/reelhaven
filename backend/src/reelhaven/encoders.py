"""Encoder families and the ffmpeg arguments to drive each kind of device.

Shared by device test encodes (devices.py) and real encodes (jobs/commands.py).
Pure functions returning argument lists.
"""

from dataclasses import dataclass
from typing import Literal

DeviceKind = Literal["nvidia", "intel", "amd", "cpu"]
Codec = Literal["hevc", "av1", "h264"]
Family = Literal["nvenc", "qsv", "vaapi", "cpu"]

CODECS: tuple[Codec, ...] = ("hevc", "av1", "h264")

ENCODER_NAMES: dict[Family, dict[Codec, str]] = {
    "nvenc": {"hevc": "hevc_nvenc", "av1": "av1_nvenc", "h264": "h264_nvenc"},
    "qsv": {"hevc": "hevc_qsv", "av1": "av1_qsv", "h264": "h264_qsv"},
    "vaapi": {"hevc": "hevc_vaapi", "av1": "av1_vaapi", "h264": "h264_vaapi"},
    "cpu": {"hevc": "libx265", "av1": "libsvtav1", "h264": "libx264"},
}


@dataclass(frozen=True)
class Device:
    id: str  # "nvidia:0", "intel:/dev/dri/renderD128", "cpu"
    kind: DeviceKind
    name: str
    family: Family
    index: int | None = None  # NVIDIA GPU index
    render_node: str | None = None  # /dev/dri/renderD*


def encoder_name(device: Device, codec: Codec) -> str:
    return ENCODER_NAMES[device.family][codec]


def hw_init_args(device: Device) -> list[str]:
    """Arguments placed before ``-i``: hardware device setup."""
    if device.family == "qsv":
        return [
            "-init_hw_device",
            f"vaapi=va:{device.render_node}",
            "-init_hw_device",
            "qsv=hw@va",
            "-filter_hw_device",
            "hw",
        ]
    if device.family == "vaapi":
        return ["-init_hw_device", f"vaapi=va:{device.render_node}", "-filter_hw_device", "va"]
    return []


def upload_filters(device: Device, ten_bit: bool) -> list[str]:
    """Filters ending the -vf chain: convert pixel format and hand frames to the GPU."""
    if device.family == "qsv":
        return [f"format={'p010le' if ten_bit else 'nv12'}", "hwupload=extra_hw_frames=64"]
    if device.family == "vaapi":
        return [f"format={'p010' if ten_bit else 'nv12'}", "hwupload"]
    # NVENC takes system-memory frames; CPU encoders likewise.
    if device.family == "nvenc":
        return [f"format={'p010le' if ten_bit else 'yuv420p'}"]
    return [f"format={'yuv420p10le' if ten_bit else 'yuv420p'}"]


def device_select_args(device: Device) -> list[str]:
    """Arguments after the encoder that pick the physical GPU."""
    if device.family == "nvenc" and device.index is not None:
        return ["-gpu", str(device.index)]
    return []


def profile_args(device: Device, codec: Codec, ten_bit: bool) -> list[str]:
    if codec == "hevc":
        return ["-profile:v", "main10" if ten_bit else "main"]
    if codec == "h264":
        return ["-profile:v", "high"]
    return []
