"""Run ffmpeg with live progress, a timeout and cancellation."""

import subprocess
import threading
import time
from collections.abc import Callable
from typing import IO

_STDERR_KEEP = 4000


class RunError(Exception):
    pass


class CancelledError(Exception):
    pass


def run_ffmpeg(
    args: list[str],
    duration_s: float | None,
    timeout_s: float,
    on_progress: Callable[[float], None] = lambda _: None,
    should_cancel: Callable[[], bool] = lambda: False,
) -> None:
    """Run ``args`` (an ffmpeg command with ``-progress pipe:1``) to completion."""
    try:
        process = subprocess.Popen(  # noqa: S603 - argument list, no shell
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL
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

    for raw in process.stdout:
        line = raw.decode("utf-8", "replace").strip()
        if line.startswith("out_time_us=") and duration_s:
            try:
                done = int(line.split("=", 1)[1]) / 1_000_000
            except ValueError:
                continue
            on_progress(max(0.0, min(done / duration_s, 1.0)))
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
