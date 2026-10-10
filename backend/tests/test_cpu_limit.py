"""CPU limiter: ReelHaven's processes run at low priority, on at most N cores."""

import json
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from reelhaven import cpu_limit
from reelhaven.cpu_limit import NICE, cores_for, preexec
from tests.helpers import API, admin_client


def test_cores_for() -> None:
    cpus = [0, 1, 2, 3, 4, 5]
    assert cores_for(None, cpus) is None
    assert cores_for(6, cpus) is None and cores_for(8, cpus) is None  # all of them: no limit
    assert cores_for(2, cpus) == frozenset({4, 5})  # the last ones
    assert cores_for(0, cpus) is None


def _child() -> dict[str, object]:
    script = (
        "import json, os; print(json.dumps({'cpus': sorted(os.sched_getaffinity(0)),"
        " 'nice': os.getpriority(os.PRIO_PROCESS, 0)}))"
    )
    result = subprocess.run(  # noqa: S603 - argument list, no shell
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        check=True,
        preexec_fn=preexec(),
    )
    data: dict[str, object] = json.loads(result.stdout)
    return data


def test_children_get_the_limits() -> None:
    available = cpu_limit.available()
    try:
        cpu_limit.set_limit(None)
        child = _child()
        assert child["cpus"] == available
        assert child["nice"] == max(NICE, os.getpriority(os.PRIO_PROCESS, 0))
        if len(available) < 2:
            pytest.skip("needs at least two CPU cores")
        cpu_limit.set_limit(1)
        assert _child()["cpus"] == available[-1:]
    finally:
        cpu_limit.set_limit(None)


def test_setting_through_the_api(client: TestClient) -> None:
    admin = admin_client(client.app)  # type: ignore[arg-type]
    devices = admin.get(f"{API}/devices").json()
    assert devices["cpu_cores_available"] == len(cpu_limit.available())
    assert devices["settings"]["cpu_cores"] is None
    body = {**devices["settings"], "cpu_cores": 1}
    try:
        assert admin.put(f"{API}/devices/settings", json=body).json()["settings"]["cpu_cores"] == 1
        expected = cores_for(1, cpu_limit.available())
        assert cpu_limit.current() == expected
    finally:
        cpu_limit.set_limit(None)
    assert admin.put(f"{API}/devices/settings", json={**body, "cpu_cores": 0}).status_code == 422
