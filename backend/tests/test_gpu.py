"""Real GPU encodes through the whole pipeline, once per GPU present.

Runs only where GPUs exist (the owner's dev container); CI has none, so
every test here is skipped there.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from reelhaven.app import create_app
from reelhaven.config import Settings
from reelhaven.devices import DeviceRegistry, detect_dri, detect_nvidia
from reelhaven.media.probe import probe
from reelhaven.scanner import Scanner
from tests.helpers import API
from tests.media_fixtures import FFMPEG
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
    application.state.scanner = Scanner(application.state.db, settings, stable_seconds=0)
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
