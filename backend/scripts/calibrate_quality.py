"""Measure every encoder on real clips and suggest quality tables (ADR-0019).

Usage: uv run python scripts/calibrate_quality.py CLIPS_DIR RESULTS.json [--analyse-only]

Each clip is encoded with every detected device and codec over a sweep of the
encoder's own quality value, using ReelHaven's real video arguments at the
"balanced" speed, and measured with XPSNR against the clip. Results are saved
as they come, so an interrupted run resumes where it stopped. The analysis then
picks, for every quality level 1-10, the GPU value whose average XPSNR matches
the CPU encoder at that level (the CPU tables in quality.py are the reference).
Clips should be real footage (10-15 s); they never go into the repo.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from itertools import pairwise
from pathlib import Path
from statistics import mean

from reelhaven.devices import DeviceRegistry
from reelhaven.encoders import (
    Codec,
    Device,
    device_select_args,
    encoder_name,
    hw_init_args,
    profile_args,
    upload_filters,
)
from reelhaven.jobs.encode_commands import _rate_control
from reelhaven.media.probe import probe
from reelhaven.quality import quality_value
from reelhaven.quality_metrics import _XPSNR, _compare

SWEEP: dict[Codec, range] = {"hevc": range(14, 39, 2), "h264": range(14, 35, 2)}
CODECS: tuple[Codec, ...] = ("hevc", "h264")


def encode(ffmpeg: str, device: Device, codec: Codec, value: int, clip: Path, out: Path) -> None:
    ten_bit = codec != "h264"
    args = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
    args += [*hw_init_args(device), "-i", str(clip), "-map", "0:v:0"]
    args += ["-vf", ",".join(upload_filters(device, ten_bit))]
    args += ["-c:v", encoder_name(device, codec), *device_select_args(device)]
    args += profile_args(device, codec, ten_bit)
    args += _rate_control(device.family, codec, value, "balanced")
    subprocess.run([*args, str(out)], check=True, capture_output=True, timeout=1800)  # noqa: S603


def xpsnr(ffmpeg: str, clip: Path, encoded: Path) -> float:
    video = probe(clip).video
    if video is None or not video.width or not video.height:
        raise SystemExit(f"{clip}: no video")
    found = _XPSNR.findall(
        _compare(ffmpeg, clip, encoded, 0.0, "xpsnr", video.width, video.height, 1800)
    )
    return 99.0 if found[-1] == "inf" else float(found[-1])


def run(clips: list[Path], results_path: Path) -> dict[str, dict[str, float]]:
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    results: dict[str, dict[str, float]] = (
        json.loads(results_path.read_text()) if results_path.exists() else {}
    )
    registry = DeviceRegistry(ffmpeg)
    registry.detect()
    devices = [(d, r) for d, r in registry.usable()]
    with tempfile.TemporaryDirectory() as tmp:
        for clip in clips:
            seconds = probe(clip).duration_s or 1
            for device, report in devices:
                for codec in CODECS:
                    if not report.supports(codec, codec != "h264"):
                        continue
                    for value in SWEEP[codec]:
                        key = f"{clip.stem}|{device.family}|{codec}|{value}"
                        if key in results:
                            continue
                        out = Path(tmp) / "out.mkv"
                        encode(ffmpeg, device, codec, value, clip, out)
                        kbps = out.stat().st_size * 8 / 1000 / seconds
                        results[key] = {"xpsnr": xpsnr(ffmpeg, clip, out), "kbps": kbps}
                        results_path.write_text(json.dumps(results, indent=1))
                        print(key, results[key], flush=True)
    return results


def curve(
    results: dict[str, dict[str, float]], family: str, codec: str
) -> dict[int, tuple[float, float]]:
    """value -> (mean XPSNR, mean kbps) over the clips measured for every value."""
    by_value: dict[int, list[dict[str, float]]] = {}
    for key, measured in results.items():
        _clip, fam, cod, value = key.split("|")
        if fam == family and cod == codec:
            by_value.setdefault(int(value), []).append(measured)
    count = max((len(v) for v in by_value.values()), default=0)
    return {
        value: (mean(m["xpsnr"] for m in ms), mean(m["kbps"] for m in ms))
        for value, ms in sorted(by_value.items())
        if len(ms) == count
    }


def at(points: dict[int, tuple[float, float]], value: float, which: int) -> float:
    """Linear interpolation of XPSNR (which=0) or kbps (which=1) at an encoder value."""
    xs = sorted(points)
    value = min(max(value, xs[0]), xs[-1])
    for lo, hi in pairwise(xs):
        if lo <= value <= hi:
            t = (value - lo) / (hi - lo)
            return points[lo][which] + t * (points[hi][which] - points[lo][which])
    return points[xs[-1]][which]


def matching_value(points: dict[int, tuple[float, float]], target: float) -> int:
    """The whole encoder value whose XPSNR is closest to ``target``."""
    candidates = range(min(points), max(points) + 1)
    return min(candidates, key=lambda v: abs(at(points, v, 0) - target))


def analyse(results: dict[str, dict[str, float]]) -> None:
    for codec in CODECS:
        reference = curve(results, "cpu", codec)
        if not reference:
            continue
        print(f"\n== {codec}: level, CPU value, XPSNR, kbps | per GPU family: value, kbps")
        families = sorted({k.split("|")[1] for k in results} - {"cpu"})
        curves = {f: curve(results, f, codec) for f in families}
        for level in range(1, 11):
            cpu_value = quality_value("cpu", codec, level)
            target = at(reference, cpu_value, 0)
            kbps = at(reference, cpu_value, 1)
            row = f"{level:>2}  cpu {cpu_value:>2}  {target:5.2f} dB  {kbps:6.0f}"
            for family, points in curves.items():
                if points:
                    v = matching_value(points, target)
                    row += f" | {family} {v:>2} {at(points, v, 0):5.2f} dB {at(points, v, 1):6.0f}"
            print(row)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    clips_dir, results_file = Path(sys.argv[1]), Path(sys.argv[2])
    if "--analyse-only" in sys.argv:
        data = json.loads(results_file.read_text())
    else:
        data = run(sorted(clips_dir.glob("*.mkv")), results_file)
    analyse(data)
