"""Run an encode: decode on the GPU when it can, otherwise on the CPU (ADR-0029)."""

import logging
from collections.abc import Callable
from pathlib import Path

from reelhaven.encoders import Device, gpu_decodes
from reelhaven.jobs.encode_commands import encode_command
from reelhaven.jobs.runner import ProgressCallback, RunError, run_ffmpeg
from reelhaven.media.info import MediaInfo
from reelhaven.planner import Plan
from reelhaven.profiles import ProfileSettings

logger = logging.getLogger(__name__)


def run_encode(
    ffmpeg: str,
    device: Device,
    source: Path,
    output: Path,
    info: MediaInfo,
    plan: Plan,
    profile: ProfileSettings,
    *,
    timeout_s: float,
    on_progress: ProgressCallback,
    should_cancel: Callable[[], bool],
    on_decoder: Callable[[str], None] = lambda _decoder: None,
) -> bool:
    """Encode ``source`` to ``output``; returns whether the GPU decoded it.

    A GPU-decoded attempt that fails (a format the card can't decode after all, a driver
    hiccup) is retried once with CPU decoding, so a file is never lost to the speed-up.
    Cancelling stops both.
    ``on_decoder`` hears "gpu" or "cpu" as each attempt starts, for the job's record.
    """
    video = info.video
    duration = info.duration_s or None
    if video is not None and gpu_decodes(device, video.codec, video.bit_depth, video.pix_fmt):
        on_decoder("gpu")
        try:
            run_ffmpeg(
                encode_command(ffmpeg, device, source, output, info, plan, profile, True),
                duration,
                timeout_s=timeout_s,
                on_progress=on_progress,
                should_cancel=should_cancel,
            )
            return True
        except RunError as exc:
            logger.warning(
                "GPU decoding failed; trying again with CPU decoding",
                extra={"path": str(source), "device": device.id, "error": str(exc)[-300:]},
            )
            output.unlink(missing_ok=True)
    on_decoder("cpu")
    run_ffmpeg(
        encode_command(ffmpeg, device, source, output, info, plan, profile),
        duration,
        timeout_s=timeout_s,
        on_progress=on_progress,
        should_cancel=should_cancel,
    )
    return False
