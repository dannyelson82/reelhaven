"""CPU limiter: every ffmpeg/ffprobe ReelHaven starts runs at low priority, and on at most
the number of CPU cores the owner allows (Hardware page).

Applied in the child process just before ffmpeg starts (``preexec_fn``): its threads are
all created afterwards, so they inherit both. Only two plain system calls run there.
"""

import os
import threading
from collections.abc import Callable

# Niceness for ReelHaven's processes: Plex, the web UI and other containers come first.
NICE = 10

_lock = threading.Lock()
_cores: frozenset[int] | None = None  # None: no limit


def available() -> list[int]:
    """The CPU cores this container may use (Unraid can pin containers to some)."""
    return sorted(os.sched_getaffinity(0))


def cores_for(limit: int | None, cpus: list[int]) -> frozenset[int] | None:
    """Which cores ``limit`` cores means: the highest-numbered ones, since the system and
    other containers tend to favour the first. None or at least all of them: no limit."""
    if limit is None or limit >= len(cpus) or limit < 1:
        return None
    return frozenset(cpus[-limit:])


def set_limit(limit: int | None) -> None:
    global _cores
    with _lock:
        _cores = cores_for(limit, available())


def current() -> frozenset[int] | None:
    with _lock:
        return _cores


def _apply(cores: frozenset[int] | None) -> None:  # runs in the child, before exec
    # Only ever lower the priority: raising it again would need privileges.
    if os.getpriority(os.PRIO_PROCESS, 0) < NICE:
        os.setpriority(os.PRIO_PROCESS, 0, NICE)
    if cores is not None:
        os.sched_setaffinity(0, cores)


def preexec() -> Callable[[], None]:
    """``preexec_fn`` for subprocess.run/Popen that applies the limits."""
    cores = current()
    return lambda: _apply(cores)
