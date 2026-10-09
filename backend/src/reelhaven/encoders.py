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
    id: str  # "nvidia:0", "intel:0000:00:02.0" (PCI slot), "cpu"
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


# --- GPU decoding (ADR-0029) ------------------------------------------------------------

# What each family's decoder handles, as (codec -> bit depths), in 4:2:0. Generations
# differ (AV1 needs an RTX 30, an Intel 11th gen or an AMD RX 6000 or newer; 12-bit HEVC
# needs a recent Intel): a file the device can't decode after all falls back to the CPU.
_HW_DECODE: dict[Family, dict[str, tuple[int, ...]]] = {
    "nvenc": {
        "h264": (8,),
        "hevc": (8, 10, 12),
        "vp9": (8, 10, 12),
        "av1": (8, 10),
        "mpeg2video": (8,),
        "vc1": (8,),
    },
    "qsv": {
        "h264": (8,),
        "hevc": (8, 10),
        "vp9": (8, 10),
        "av1": (8, 10),
        "mpeg2video": (8,),
        "vc1": (8,),
    },
    "vaapi": {
        "h264": (8,),
        "hevc": (8, 10),
        "vp9": (8, 10),
        "av1": (8, 10),
        "mpeg2video": (8,),
        "vc1": (8,),
    },
}


def gpu_decodes(
    device: Device, codec: str | None, bit_depth: int | None, pix_fmt: str | None
) -> bool:
    """Whether to decode the source on ``device`` itself. Unknown chroma (older scans) is
    taken as 4:2:0, the norm; a wrong guess only costs a retry with CPU decoding."""
    table = _HW_DECODE.get(device.family)
    if table is None or codec not in table:
        return False
    if pix_fmt is not None and ("422" in pix_fmt or "444" in pix_fmt or "440" in pix_fmt):
        return False
    return (bit_depth or 8) in table[codec]


def gpu_decode_args(device: Device) -> list[str]:
    """Arguments before ``-i`` that decode on the GPU and keep the frames there."""
    if device.family == "qsv":
        return [*hw_init_args(device), "-hwaccel", "qsv", "-hwaccel_device", "hw",
                "-hwaccel_output_format", "qsv"]  # fmt: skip
    if device.family == "vaapi":
        return [*hw_init_args(device), "-hwaccel", "vaapi", "-hwaccel_device", "va",
                "-hwaccel_output_format", "vaapi"]  # fmt: skip
    return [
        "-hwaccel",
        "cuda",
        "-hwaccel_device",
        str(device.index or 0),
        "-hwaccel_output_format",
        "cuda",
    ]


def scaled_width(width: int, height: int, target_height: int) -> int:
    """The width keeping the picture's proportions at ``target_height``, rounded to even."""
    return max(2, round(width * target_height / height / 2) * 2)


def gpu_video_filters(device: Device, size: tuple[int, int] | None, ten_bit: bool) -> list[str]:
    """Scale (to ``size`` = width, height) and set the bit depth on the GPU, so the frames
    never leave it."""
    if device.family == "qsv":
        options = [f"w={size[0]}:h={size[1]}"] if size else []
        options.append(f"format={'p010' if ten_bit else 'nv12'}")
        return [f"vpp_qsv={':'.join(options)}"]
    if device.family == "vaapi":
        options = [f"w={size[0]}:h={size[1]}"] if size else []
        options.append(f"format={'p010' if ten_bit else 'nv12'}")
        return [f"scale_vaapi={':'.join(options)}"]
    options = [f"w=-2:h={size[1]}:interp_algo=lanczos"] if size else []
    options.append(f"format={'p010le' if ten_bit else 'nv12'}")
    return [f"scale_cuda={':'.join(options)}"]
