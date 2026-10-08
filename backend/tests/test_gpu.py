"""Real GPU encodes through the whole pipeline, once per GPU present.

Runs only where GPUs exist (the owner's dev container); CI has none, so
every test here is skipped there.
"""

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from reelhaven.app import create_app
from reelhaven.config import Settings
from reelhaven.devices import DeviceRegistry, detect_dri, detect_nvidia
from reelhaven.jobs import encode_run
from reelhaven.jobs.encode_commands import expected_encode_layout, expected_video
from reelhaven.jobs.runner import run_ffmpeg
from reelhaven.jobs.verify import verify_output
from reelhaven.media.probe import probe
from reelhaven.planner import plan_file
from reelhaven.policy import LanguagePolicy
from reelhaven.profiles import ProfileSettings
from reelhaven.scanner import Scanner
from tests.helpers import API
from tests.media_fixtures import FFMPEG, Spec, make
from tests.test_encode_pipeline import FAST, file_id, last_job, setup

# Cheap: lists devices without test encodes, so collection stays fast in CI.
GPUS = [d.id for d in (*detect_nvidia(), *detect_dri())] if FFMPEG else []
pytestmark = pytest.mark.skipif(not GPUS, reason="no GPU")


@pytest.fixture(scope="module")
def registry() -> DeviceRegistry:
    devices = DeviceRegistry(FFMPEG or "ffmpeg")
    devices.detect()  # the real test encodes, once for the module
    return devices


@pytest.fixture
def gpu_app(settings: Settings, registry: DeviceRegistry) -> Iterator[FastAPI]:
    settings = settings.model_copy(
        update={"transcode_dir": settings.config_dir.parent / "transcode"}
    )
    application = create_app(settings, gateways=frozenset(), detect_devices=False)
    application.state.scanner = Scanner(
        application.state.db,
        settings,
        stable_seconds=0,
        resolve_languages=application.state.scanner._resolve_languages,
    )
    application.state.devices = registry
    application.state.queue = type(application.state.queue)(
        application.state.db, settings, registry
    )
    with TestClient(application):
        yield application


def only(admin: TestClient, gpu: str) -> None:
    """Switch every other device off, so the job has to run on ``gpu``."""
    others = {other: {"enabled": False} for other in GPUS if other != gpu}
    response = admin.put(
        f"{API}/devices/settings",
        json={"cpu_enabled": False, "cpu_concurrency": 1, "devices": others},
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("gpu", GPUS)
@pytest.mark.parametrize("ten_bit", [True, False])
def test_gpu_encode(gpu_app: FastAPI, settings: Settings, gpu: str, ten_bit: bool) -> None:
    admin, lib, path = setup(gpu_app, settings, {**FAST, "ten_bit": ten_bit}, cpu=False)
    only(admin, gpu)
    before = path.stat().st_size
    assert admin.post(f"{API}/files/{file_id(admin, lib)}/apply").status_code == 201
    assert gpu_app.state.queue.wait_idle(180)
    job = last_job(admin)
    assert (job["status"], job["outcome"], job["device"]) == ("done", "replaced", gpu), job
    info = probe(path)
    assert info.video is not None
    assert (info.video.codec, info.video.bit_depth) == ("hevc", 10 if ten_bit else 8)
    assert path.stat().st_size < before


@pytest.mark.parametrize("gpu", GPUS)
def test_gpu_test_run(gpu_app: FastAPI, settings: Settings, gpu: str) -> None:
    admin, lib, _path = setup(gpu_app, settings, FAST, cpu=False)
    only(admin, gpu)
    assert admin.post(f"{API}/libraries/{lib}/test-run", json={}).status_code == 201
    assert gpu_app.state.queue.wait_idle(180)
    run = admin.get(f"{API}/libraries/{lib}/test-run").json()["run"]
    (sample,) = run["samples"]
    assert run["status"] == "done", sample
    result = sample["result"]
    assert result["device"] == gpu
    assert result["xpsnr"] is not None and result["ssim"] is not None


# --- GPU decoding (ADR-0029) ---------------------------------------------------------------

NVIDIA_GPUS = [g for g in GPUS if g.startswith("nvidia:")]


def spy_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Record every encode command while still running it for real."""
    calls: list[list[str]] = []
    real = run_ffmpeg

    def spy(args: list[str], *rest: Any, **kwargs: Any) -> None:
        calls.append(args)
        real(args, *rest, **kwargs)

    monkeypatch.setattr(encode_run, "run_ffmpeg", spy)
    return calls


@pytest.mark.parametrize("gpu", NVIDIA_GPUS)
def test_nvidia_decodes_on_the_gpu(
    gpu_app: FastAPI, settings: Settings, gpu: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = spy_ffmpeg(monkeypatch)
    admin, lib, _path = setup(gpu_app, settings, FAST, cpu=False)
    only(admin, gpu)
    assert admin.post(f"{API}/files/{file_id(admin, lib)}/apply").status_code == 201
    assert gpu_app.state.queue.wait_idle(180)
    job = last_job(admin)
    assert (job["status"], job["outcome"]) == ("done", "replaced"), job
    assert len(calls) == 1 and "cuda" in calls[0]  # decoded on the card


@pytest.mark.parametrize("gpu", NVIDIA_GPUS)
def test_hdr10_survives_gpu_decoding(
    tmp_path: Path, registry: DeviceRegistry, gpu: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = spy_ffmpeg(monkeypatch)
    source = make(tmp_path / "hdr.mkv", Spec(codec="libx265", hdr10=True, size="1920x1080"))
    info = probe(source)
    assert info.video is not None and info.video.hdr == "hdr10"
    profile = ProfileSettings.model_validate({**FAST, "max_height": 720})
    p = plan_file(info, "eng", LanguagePolicy(), profile)
    output = tmp_path / "out" / "hdr.mkv"
    output.parent.mkdir()
    device = next(d for d, _report in registry.usable() if d.id == gpu)
    assert encode_run.run_encode(
        FFMPEG or "ffmpeg", device, source, output, info, p, profile,
        timeout_s=300, on_progress=lambda *_: None, should_cancel=lambda: False,
    )  # fmt: skip
    assert "cuda" in calls[0]
    verify_output(
        output, info, expected_encode_layout(source, info, p, profile),
        FFMPEG or "ffmpeg", "ffprobe", expected_video=expected_video(info, profile),
    )  # fmt: skip  # raises if HDR10 was lost


@pytest.mark.parametrize("gpu", NVIDIA_GPUS)
def test_a_file_the_card_cant_decode_falls_back_to_the_cpu(
    tmp_path: Path, registry: DeviceRegistry, gpu: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = spy_ffmpeg(monkeypatch)
    source = tmp_path / "hi10p.mkv"
    subprocess.run(  # noqa: S603 - argument list, no shell
        [FFMPEG or "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=d=2:s=640x360",
         "-c:v", "libx264", "-pix_fmt", "yuv420p10le", str(source)],
        check=True,
    )  # fmt: skip
    info = probe(source)
    assert info.video is not None and info.video.bit_depth == 10
    # Pretend it's 8-bit so the GPU is tried (as with a file scanned before ADR-0029).
    info.video.bit_depth, info.video.pix_fmt = 8, None
    profile = ProfileSettings.model_validate(FAST)
    p = plan_file(info, "eng", LanguagePolicy(), profile)
    output = tmp_path / "out" / "hi10p.mkv"
    output.parent.mkdir()
    device = next(d for d, _report in registry.usable() if d.id == gpu)
    decoded_on_gpu = encode_run.run_encode(
        FFMPEG or "ffmpeg", device, source, output, info, p, profile,
        timeout_s=300, on_progress=lambda *_: None, should_cancel=lambda: False,
    )  # fmt: skip
    assert decoded_on_gpu is False
    assert ["cuda" in c for c in calls] == [True, False]
    out = probe(output)
    assert out.video is not None and out.video.codec == "hevc"
