import os
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from reelhaven.app import create_app
from reelhaven.config import Settings
from reelhaven.devices import (
    CPU,
    DeviceRegistry,
    detect_dri,
    detect_nvidia,
    first_error,
    probe_device,
    trial_encode_command,
)
from reelhaven.encoders import Device
from tests.helpers import API, admin_client
from tests.media_fixtures import FFMPEG

NVIDIA = Device(id="nvidia:0", kind="nvidia", name="RTX 3060", family="nvenc", index=0)
INTEL = Device(
    id="intel:0000:00:02.0",
    kind="intel",
    name="Intel",
    family="qsv",
    render_node="/dev/dri/renderD128",
)
AMD = Device(
    id="amd:0000:03:00.0",
    kind="amd",
    name="AMD",
    family="vaapi",
    render_node="/dev/dri/renderD129",
)


def test_detect_nvidia_parses_nvidia_smi() -> None:
    def fake(args: list[str], timeout: float) -> tuple[int, str, str]:
        assert args[1:] == ["--query-gpu=index,name", "--format=csv,noheader"]
        return 0, "0, NVIDIA GeForce RTX 3060\n1, Quadro P2000\n", ""

    devices = detect_nvidia(run=fake)
    assert [(d.id, d.name, d.index) for d in devices] == [
        ("nvidia:0", "NVIDIA GeForce RTX 3060", 0),
        ("nvidia:1", "Quadro P2000", 1),
    ]


def test_no_nvidia() -> None:
    assert detect_nvidia(run=lambda args, timeout: (127, "", "not found")) == []


def test_detect_dri_by_vendor(tmp_path: Path) -> None:
    dev, sysfs, pci = tmp_path / "dev", tmp_path / "sys", tmp_path / "pci"
    dev.mkdir()
    sysfs.mkdir()
    for node, vendor, slot in (
        ("renderD128", "0x10de", "0000:01:00.0"),
        ("renderD129", "0x8086", "0000:00:02.0"),
        ("renderD130", "0x1002", None),  # no PCI link: falls back to the node name
    ):
        (dev / node).touch()
        if slot:
            (pci / slot).mkdir(parents=True)
            (sysfs / node).mkdir()
            (sysfs / node / "device").symlink_to(pci / slot)
        else:
            (sysfs / node / "device").mkdir(parents=True)
        (sysfs / node / "device" / "vendor").write_text(vendor + "\n")
    devices = detect_dri(sysfs, dev)
    assert [(d.id, d.kind, d.family, d.render_node, d.name) for d in devices] == [
        ("intel:0000:00:02.0", "intel", "qsv", str(dev / "renderD129"), "Intel GPU (0000:00:02.0)"),
        ("amd:renderD130", "amd", "vaapi", str(dev / "renderD130"), "AMD GPU (renderD130)"),
    ]  # the NVIDIA node is used through NVENC instead


def test_gpu_trial_encode_commands() -> None:
    assert trial_encode_command("ffmpeg", NVIDIA, "hevc", True) == [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=1280x720:rate=30:duration=1",
        "-vf",
        "format=p010le",
        "-c:v",
        "hevc_nvenc",
        "-gpu",
        "0",
        "-profile:v",
        "main10",
        "-f",
        "null",
        "-",
    ]
    assert trial_encode_command("ffmpeg", INTEL, "av1", False) == [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-v",
        "error",
        "-init_hw_device",
        "vaapi=va:/dev/dri/renderD128",
        "-init_hw_device",
        "qsv=hw@va",
        "-filter_hw_device",
        "hw",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=1280x720:rate=30:duration=1",
        "-vf",
        "format=nv12,hwupload=extra_hw_frames=64",
        "-c:v",
        "av1_qsv",
        "-f",
        "null",
        "-",
    ]
    assert "-vf" in trial_encode_command("ffmpeg", AMD, "hevc", True)
    assert "format=p010,hwupload" in trial_encode_command("ffmpeg", AMD, "hevc", True)


def test_probe_records_failures() -> None:
    def fake(args: list[str], timeout: float) -> tuple[int, str, str]:
        return (0, "", "") if "hevc_nvenc" in args else (1, "", "No capable devices found")

    report = probe_device(NVIDIA, "ffmpeg", run=fake)
    assert report.supports("hevc", False) and report.supports("hevc", True)
    assert not report.supports("av1", False)
    av1 = next(r for r in report.results if r.codec == "av1")
    assert av1.error == "No capable devices found"


@pytest.mark.skipif(FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed")
def test_cpu_encoders_really_work() -> None:
    report = probe_device(CPU, FFMPEG or "ffmpeg")
    for codec, ten_bit in (("hevc", False), ("hevc", True), ("h264", False)):
        assert report.supports(codec, ten_bit), [r for r in report.results if not r.ok]


def test_devices_api(settings: Settings) -> None:
    app: FastAPI = create_app(settings, gateways=frozenset(), detect_devices=False)
    calls: list[list[str]] = []

    def fake(args: list[str], timeout: float) -> tuple[int, str, str]:
        calls.append(args)
        if args[0] == "nvidia-smi":
            return 0, "0, RTX 3060\n", ""
        return 0, "", ""

    app.state.devices = DeviceRegistry("ffmpeg", run=fake, dev=settings.config_dir / "no-dri")
    with TestClient(app):
        admin = admin_client(app)
        app.state.devices.detect()
        body = admin.get(f"{API}/devices").json()
        ids = [d["id"] for d in body["devices"]]
        assert ids == ["nvidia:0", "cpu"]
        cpu = body["devices"][1]
        assert cpu["enabled"] is False  # CPU encoding off by default
        assert all(r["ok"] for r in body["devices"][0]["results"])

        new = {
            "cpu_enabled": True,
            "cpu_concurrency": 1,
            "devices": {"nvidia:0": {"enabled": True, "concurrency": 3}},
        }
        saved = admin.put(f"{API}/devices/settings", json=new).json()
        assert [(d["id"], d["enabled"], d["concurrency"]) for d in saved["devices"]] == [
            ("nvidia:0", True, 3),
            ("cpu", True, 1),
        ]
        bad = {**new, "devices": {"nvidia:0": {"enabled": True, "concurrency": 50}}}
        assert admin.put(f"{API}/devices/settings", json=bad).status_code == 422
        assert admin.post(f"{API}/devices/detect").status_code == 202


def test_detect_nvidia_reads_real_output(tmp_path: Path) -> None:
    """Through a real subprocess: the GPU list is on stdout, warnings on stderr."""
    smi = tmp_path / "nvidia-smi"
    smi.write_text(
        "#!/bin/sh\necho '0, NVIDIA GeForce RTX 3060'\necho 'a warning' >&2\n", encoding="utf-8"
    )
    smi.chmod(0o755)
    assert [d.id for d in detect_nvidia(str(smi))] == ["nvidia:0"]


@pytest.mark.skipif(shutil.which("nvidia-smi") is None or FFMPEG is None, reason="no NVIDIA GPU")
def test_nvidia_really_works() -> None:
    """Only where a GPU exists (the owner's dev container, not CI)."""
    devices = detect_nvidia()
    assert devices
    report = probe_device(devices[0], FFMPEG or "ffmpeg")
    for codec, ten_bit in (("hevc", False), ("hevc", True), ("h264", False)):
        assert report.supports(codec, ten_bit), [r for r in report.results if not r.ok]


def test_first_error_is_the_cause() -> None:
    stderr = (
        "[av1_nvenc @ 0x562bcfa2ef00] No capable devices found\n"
        "[vost#0:0/av1_nvenc @ 0x5629] [enc:av1_nvenc @ 0x5628] Error while opening encoder\n"
        "[out#0/null @ 0x562bcfa2e580] Nothing was written into output file\n"
    )
    assert first_error(stderr) == "No capable devices found"
    qsv = (
        "libva info: VA-API version 1.24.0\n"
        "libva info: va_openDriver() returns 0\n"
        "[av1_qsv @ 0x55d9217f45c0] This version of runtime doesn't support AV1 encoding\n"
    )
    assert first_error(qsv) == "This version of runtime doesn't support AV1 encoding"
    assert first_error("\n  \n") == ""
    assert first_error("plain message") == "plain message"
