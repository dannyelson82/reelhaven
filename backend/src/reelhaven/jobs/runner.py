"""Run ffmpeg with live progress, a timeout and cancellation."""

import subprocess
import threading
import time
from collections.abc import Callable
from typing import IO, Protocol

from reelhaven.cpu_limit import preexec

_STDERR_KEEP = 4000


class ProgressCallback(Protocol):
    def __call__(
        self, fraction: float, fps: float | None = None, speed: float | None = None
    ) -> None: ...


def _ignore(fraction: float, fps: float | None = None, speed: float | None = None) -> None:
    pass


class RunError(Exception):
    pass


class CancelledError(Exception):
    pass


def run_ffmpeg(
    args: list[str],
    duration_s: float | None,
    timeout_s: float,
    on_progress: ProgressCallback = _ignore,
    should_cancel: Callable[[], bool] = lambda: False,
) -> None:
    """Run ``args`` (an ffmpeg command with ``-progress pipe:1``) to completion."""
    try:
        process = subprocess.Popen(  # noqa: S603 - argument list, no shell
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            preexec_fn=preexec(),
        )
    except OSError as exc:
        raise RunError(f"could not start ffmpeg: {exc}") from exc

    stderr_chunks: list[bytes] = []

    def drain_stderr(stream: IO[bytes]) -> None:
        for chunk in iter(lambda: stream.read(4096), b""):
            stderr_chunks.append(chunk)

    assert process.stdout is not None and process.stderr is not None  # noqa: S101
    reader = threading.Thread(target=drain_stderr, args=(process.stderr,), daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout_s

    def watchdog() -> None:
        while process.poll() is None:
            if should_cancel() or time.monotonic() > deadline:
                process.kill()
                return
            time.sleep(0.25)

    guard = threading.Thread(target=watchdog, daemon=True)
    guard.start()

    block: dict[str, str] = {}
    for raw in process.stdout:
        key, _, value = raw.decode("utf-8", "replace").strip().partition("=")
        block[key] = value
        if key != "progress":
            continue
        # End of one progress block: out_time_us, fps and speed belong together.
        done = _number(block.get("out_time_us"))
        fps = _number(block.get("fps")) or None
        speed = _number((block.get("speed") or "").rstrip("x")) or None
        if done is not None and duration_s:
            on_progress(max(0.0, min(done / 1_000_000 / duration_s, 1.0)), fps, speed)
        block = {}
    process.wait()
    guard.join(timeout=1)
    reader.join(timeout=1)

    if should_cancel():
        raise CancelledError
    if time.monotonic() > deadline and process.returncode != 0:
        raise RunError(f"ffmpeg took longer than {timeout_s:.0f}s and was stopped")
    if process.returncode != 0:
        stderr = b"".join(stderr_chunks).decode("utf-8", "replace").strip()
        raise RunError(stderr[-_STDERR_KEEP:] or f"ffmpeg exited with code {process.returncode}")
    on_progress(1.0)


def _number(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "", "N/A") else None
    except ValueError:
        return None
