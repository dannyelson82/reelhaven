"""Live job updates for the UI (ARCHITECTURE.md §11.1): who to wake when jobs change."""

import asyncio
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress


def eta_seconds(progress: float, elapsed_s: float) -> int | None:
    """Time left for a running job, extrapolated from its progress so far.

    None until there is enough to go on: early numbers swing wildly.
    """
    if not 0.02 <= progress < 1 or elapsed_s < 10:
        return None
    return round(elapsed_s * (1 - progress) / progress)


class ChangeFeed:
    """Wakes WebSocket handlers when jobs change. ``changed`` is safe from any thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listeners: set[tuple[asyncio.AbstractEventLoop, asyncio.Event]] = set()

    def changed(self) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for loop, wake in listeners:
            with suppress(RuntimeError):  # that event loop has shut down
                loop.call_soon_threadsafe(wake.set)

    @contextmanager
    def listen(self) -> Iterator[asyncio.Event]:
        """An event that is set after each change, while the block runs (call in a coroutine)."""
        key = (asyncio.get_running_loop(), asyncio.Event())
        with self._lock:
            self._listeners.add(key)
        try:
            yield key[1]
        finally:
            with self._lock:
                self._listeners.discard(key)
