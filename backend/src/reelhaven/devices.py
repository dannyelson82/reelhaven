"""Encode device detection (ARCHITECTURE.md §6.5).

Finds NVIDIA GPUs (nvidia-smi) and Intel/AMD GPUs (/dev/dri render nodes and
their PCI vendor), then proves each one with a one-second test encode per
codec, because what a GPU claims and what works in a container differ.
"""

import logging
import re
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from reelhaven.encoders import (
    CODECS,
    Codec,
    Device,
    DeviceKind,
    device_select_args,
    encoder_name,
    hw_init_args,
    profile_args,
    upload_filters,
)

logger = logging.getLogger(__name__)

_PCI_SLOT = re.compile(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]")
PCI_VENDORS = {"0x8086": "intel", "0x1002": "amd", "0x10de": "nvidia"}
TEST_TIMEOUT_S = 30


@dataclass
class CodecResult:
    codec: str
    ten_bit: bool
    encoder: str
    ok: bool
    error: str | None = None
    seconds: float | None = None


@dataclass
class DeviceReport:
    id: str
    kind: str
    name: str
    family: str
    results: list[CodecResult] = field(default_factory=list)

    def supports(self, codec: str, ten_bit: bool) -> bool:
        return any(r.ok for r in self.results if r.codec == codec and r.ten_bit == ten_bit)


# (exit code, stdout, stderr)
Runner = Callable[[list[str], float], tuple[int, str, str]]


def _run(args: list[str], timeout: float) -> tuple[int, str, str]:
    try:
        result = subprocess.run(  # noqa: S603 - argument list, no shell
            args, capture_output=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout:.0f}s"
    except OSError as exc:
        return 127, "", str(exc)
    return (
        result.returncode,
        result.stdout.decode("utf-8", "replace"),
        result.stderr.decode("utf-8", "replace"),
    )


def detect_nvidia(nvidia_smi: str = "nvidia-smi", run: Runner = _run) -> list[Device]:
    # The list is on stdout; reading stderr here once hid every NVIDIA card.
    code, output, _ = run([nvidia_smi, "--query-gpu=index,name", "--format=csv,noheader"], 10)
    if code != 0:
        return []
    devices = []
    for line in output.splitlines():
        parts = [p.strip() for p in line.split(",", 1)]
        if len(parts) == 2 and parts[0].isdigit():
            devices.append(
                Device(
                    id=f"nvidia:{parts[0]}",
                    kind="nvidia",
                    name=parts[1],
                    family="nvenc",
                    index=int(parts[0]),
                )
            )
    return devices


def _pci_slot(sysfs: Path, node: str) -> str | None:
    """The GPU's PCI address, e.g. 0000:00:02.0: stable, unlike renderD numbers,
    which shift when another GPU is added or the BIOS changes."""
    try:
        slot = (sysfs / node / "device").resolve(strict=True).name
    except OSError:
        return None
    return slot if _PCI_SLOT.fullmatch(slot) else None


def detect_dri(sysfs: Path = Path("/sys/class/drm"), dev: Path = Path("/dev/dri")) -> list[Device]:
    """Intel and AMD render nodes (NVIDIA nodes are handled through NVENC)."""
    devices = []
    for node in sorted(dev.glob("renderD*")):
        vendor_file = sysfs / node.name / "device" / "vendor"
        try:
            vendor = PCI_VENDORS.get(vendor_file.read_text().strip().lower())
        except OSError:
            vendor = None
        if vendor not in ("intel", "amd"):
            continue
        kind: DeviceKind = "intel" if vendor == "intel" else "amd"
        slot = _pci_slot(sysfs, node.name) or node.name
        devices.append(
            Device(
                id=f"{kind}:{slot}",
                kind=kind,
                name=f"{'Intel' if kind == 'intel' else 'AMD'} GPU ({slot})",
                family="qsv" if kind == "intel" else "vaapi",
                render_node=str(node),
            )
        )
    return devices


CPU = Device(id="cpu", kind="cpu", name="CPU (software)", family="cpu")


def trial_encode_command(ffmpeg: str, device: Device, codec: Codec, ten_bit: bool) -> list[str]:
    vf = ",".join(upload_filters(device, ten_bit))
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-v", "error",
        *hw_init_args(device),
        "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=1",
        "-vf", vf,
        "-c:v", encoder_name(device, codec),
        *device_select_args(device),
        *profile_args(device, codec, ten_bit),
        "-f", "null", "-",
    ]  # fmt: skip


_PREFIX = re.compile(r"^(\[[^\]]*\]\s*)+")


def first_error(stderr: str) -> str:
    """ffmpeg's first error line is the cause; the rest are its consequences."""
    for line in stderr.splitlines():
        text = _PREFIX.sub("", line).strip()
        if text and not text.startswith("libva info:"):  # VA-API chatter, not an error
            return text[:400]
    return ""


def probe_device(device: Device, ffmpeg: str, run: Runner = _run) -> DeviceReport:
    report = DeviceReport(device.id, device.kind, device.name, device.family)
    for codec in CODECS:
        for ten_bit in (False, True) if codec != "h264" else (False,):
            started = time.monotonic()
            code, _, stderr = run(
                trial_encode_command(ffmpeg, device, codec, ten_bit), TEST_TIMEOUT_S
            )
            ok = code == 0
            report.results.append(
                CodecResult(
                    codec=codec,
                    ten_bit=ten_bit,
                    encoder=encoder_name(device, codec),
                    ok=ok,
                    error=None if ok else first_error(stderr) or f"exit code {code}",
                    seconds=round(time.monotonic() - started, 2),
                )
            )
    return report


class DeviceRegistry:
    """Detected devices and their test results; detection runs in the background."""

    def __init__(
        self,
        ffmpeg: str,
        nvidia_smi: str = "nvidia-smi",
        run: Runner = _run,
        sysfs: Path = Path("/sys/class/drm"),
        dev: Path = Path("/dev/dri"),
    ) -> None:
        self._ffmpeg = ffmpeg
        self._nvidia_smi = nvidia_smi
        self._run = run
        self._sysfs = sysfs
        self._dev = dev
        self._lock = threading.Lock()
        self._reports: list[DeviceReport] = []
        self._devices: dict[str, Device] = {}
        self._detecting = False
        self.detected_at: float | None = None

    @property
    def detecting(self) -> bool:
        return self._detecting

    def reports(self) -> list[DeviceReport]:
        with self._lock:
            return list(self._reports)

    def detect(self) -> list[DeviceReport]:
        self._detecting = True
        try:
            devices = [
                *detect_nvidia(self._nvidia_smi, self._run),
                *detect_dri(self._sysfs, self._dev),
                CPU,
            ]
            reports = [probe_device(d, self._ffmpeg, self._run) for d in devices]
            with self._lock:
                self._reports = reports
                self._devices = {d.id: d for d in devices}
                self.detected_at = time.time()
            logger.info(
                "devices detected",
                extra={
                    "devices": [
                        {
                            "id": r.id,
                            "ok": [
                                f"{c.codec}{'10' if c.ten_bit else ''}" for c in r.results if c.ok
                            ],
                        }
                        for r in reports
                    ]
                },
            )
            return reports
        finally:
            self._detecting = False

    def detect_in_background(self) -> bool:
        if self._detecting:
            return False
        threading.Thread(target=self.detect, name="detect-devices", daemon=True).start()
        return True

    def usable(self) -> list[tuple[Device, DeviceReport]]:
        """Detected devices with their test results."""
        with self._lock:
            return [(self._devices[r.id], r) for r in self._reports if r.id in self._devices]

    def as_dicts(self) -> list[dict[str, object]]:
        return [asdict(r) for r in self.reports()]
