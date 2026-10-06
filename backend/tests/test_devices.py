import os
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
    probe_device,
    trial_encode_command,
)
from reelhaven.encoders import Device
from tests.helpers import API, admin_client
from tests.media_fixtures import FFMPEG

NVIDIA = Device(id="nvidia:0", kind="nvidia", name="RTX 3060", family="nvenc", index=0)
INTEL = Device(
    id="intel:/dev/dri/renderD128",
    kind="intel",
    name="Intel",
    family="qsv",
    render_node="/dev/dri/renderD128",
)
AMD = Device(
    id="amd:/dev/dri/renderD129",
    kind="amd",
    name="AMD",
    family="vaapi",
    render_node="/dev/dri/renderD129",
)


def test_detect_nvidia_parses_nvidia_smi() -> None:
    def fake(args: list[str], timeout: float) -> tuple[int, str]:
        assert args[1:] == ["--query-gpu=index,name", "--format=csv,noheader"]
        return 0, "0, NVIDIA GeForce RTX 3060\n1, Quadro P2000\n"

    devices = detect_nvidia(run=fake)
    assert [(d.id, d.name, d.index) for d in devices] == [
        ("nvidia:0", "NVIDIA GeForce RTX 3060", 0),
        ("nvidia:1", "Quadro P2000", 1),
    ]


def test_no_nvidia() -> None:
    assert detect_nvidia(run=lambda args, timeout: (127, "not found")) == []


def test_detect_dri_by_vendor(tmp_path: Path) -> None:
    dev, sysfs = tmp_path / "dev", tmp_path / "sys"
    dev.mkdir()
    for node, vendor in (
        ("renderD128", "0x8086"),
        ("renderD129", "0x1002"),
        ("renderD130", "0x10de"),
    ):
        (dev / node).touch()
        (sysfs / node / "device").mkdir(parents=True)
        (sysfs / node / "device" / "vendor").write_text(vendor + "\n")
    devices = detect_dri(sysfs, dev)
    assert [(d.kind, d.family, d.render_node) for d in devices] == [
        ("intel", "qsv", str(dev / "renderD128")),
        ("amd", "vaapi", str(dev / "renderD129")),
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
    def fake(args: list[str], timeout: float) -> tuple[int, str]:
        return (0, "") if "hevc_nvenc" in args else (1, "No capable devices found")

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

    def fake(args: list[str], timeout: float) -> tuple[int, str]:
        calls.append(args)
        if args[0] == "nvidia-smi":
            return 0, "0, RTX 3060\n"
        return 0, ""

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
