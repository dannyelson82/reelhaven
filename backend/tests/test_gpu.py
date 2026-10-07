"""Real GPU encodes through the whole pipeline.

Runs only where a GPU is present (the owner's dev container); CI has none.
"""

import shutil
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from reelhaven.app import create_app
from reelhaven.config import Settings
from reelhaven.devices import DeviceRegistry
from reelhaven.media.probe import probe
from reelhaven.scanner import Scanner
from tests.helpers import API
from tests.media_fixtures import FFMPEG
from tests.test_encode_pipeline import FAST, file_id, last_job, setup

pytestmark = pytest.mark.skipif(
    shutil.which("nvidia-smi") is None or FFMPEG is None, reason="no NVIDIA GPU"
)


@pytest.fixture
def gpu_app(settings: Settings) -> Iterator[FastAPI]:
    settings = settings.model_copy(
        update={"transcode_dir": settings.config_dir.parent / "transcode"}
    )
    application = create_app(settings, gateways=frozenset(), detect_devices=False)
    application.state.scanner = Scanner(application.state.db, settings, stable_seconds=0)
    application.state.devices = DeviceRegistry(FFMPEG or "ffmpeg")
    application.state.devices.detect()
    application.state.queue = type(application.state.queue)(
        application.state.db, settings, application.state.devices
    )
    with TestClient(application):
        yield application


@pytest.mark.parametrize("ten_bit", [True, False])
def test_nvenc_encode(gpu_app: FastAPI, settings: Settings, ten_bit: bool) -> None:
    admin, lib, path = setup(gpu_app, settings, {**FAST, "ten_bit": ten_bit}, cpu=False)
    before = path.stat().st_size
    assert admin.post(f"{API}/files/{file_id(admin, lib)}/apply").status_code == 201
    assert gpu_app.state.queue.wait_idle(180)
    job = last_job(admin)
    assert (job["status"], job["outcome"], job["device"]) == ("done", "replaced", "nvidia:0"), job
    info = probe(path)
    assert info.video is not None
    assert (info.video.codec, info.video.bit_depth) == ("hevc", 10 if ten_bit else 8)
    assert path.stat().st_size < before


def test_nvenc_test_run(gpu_app: FastAPI, settings: Settings) -> None:
    admin, lib, _path = setup(gpu_app, settings, FAST, cpu=False)
    assert admin.post(f"{API}/libraries/{lib}/test-run", json={}).status_code == 201
    assert gpu_app.state.queue.wait_idle(180)
    run = admin.get(f"{API}/libraries/{lib}/test-run").json()["run"]
    (sample,) = run["samples"]
    assert run["status"] == "done", sample
    result = sample["result"]
    assert result["device"] == "nvidia:0"
    assert result["xpsnr"] is not None and result["ssim"] is not None
