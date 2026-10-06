"""Generate tiny synthetic media files with ffmpeg for tests.

Never real media: every file is a 1-second test pattern with sine-tone audio
and short SRT subtitles, built from a declarative spec.
"""

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

FFMPEG = shutil.which("ffmpeg")


@dataclass
class Audio:
    language: str | None = "eng"
    title: str | None = None
    default: bool = False
    comment: bool = False
    channels: int = 2


@dataclass
class Sub:
    language: str | None = "eng"
    title: str | None = None
    default: bool = False
    forced: bool = False
    hearing_impaired: bool = False


@dataclass
class Spec:
    audio: list[Audio] = field(default_factory=lambda: [Audio()])
    subs: list[Sub] = field(default_factory=list)
    codec: str = "libx264"
    size: str = "160x90"
    seconds: float = 1.0


def make(path: Path, spec: Spec) -> Path:
    """Write ``path`` (container chosen by extension) according to ``spec``."""
    assert FFMPEG, "ffmpeg is required for media tests"
    srt = path.parent / f".{path.name}.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:00,900\nHello\n")
    args = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
    args += ["-f", "lavfi", "-i", f"testsrc2=size={spec.size}:rate=10:duration={spec.seconds}"]
    for i, _ in enumerate(spec.audio):
        args += ["-f", "lavfi", "-i", f"sine=frequency={300 + 50 * i}:duration={spec.seconds}"]
    for _ in spec.subs:
        args += ["-i", str(srt)]
    args += ["-map", "0:v"]
    for i in range(len(spec.audio)):
        args += ["-map", f"{i + 1}:a"]
    for i in range(len(spec.subs)):
        args += ["-map", f"{len(spec.audio) + 1 + i}:s"]
    args += ["-c:v", spec.codec, "-preset", "ultrafast"]
    if spec.codec == "libx265":
        args += ["-x265-params", "log-level=error"]
    args += ["-c:a", "aac", "-b:a", "48k"]
    args += ["-c:s", "mov_text" if path.suffix == ".mp4" else "srt"]
    for i, audio in enumerate(spec.audio):
        args += [f"-ac:a:{i}", str(audio.channels)]
        if audio.language:
            args += [f"-metadata:s:a:{i}", f"language={audio.language}"]
        if audio.title:
            args += [f"-metadata:s:a:{i}", f"title={audio.title}"]
        flags = [f for f, on in (("default", audio.default), ("comment", audio.comment)) if on]
        args += [f"-disposition:a:{i}", "+".join(flags) or "0"]
    for i, sub in enumerate(spec.subs):
        if sub.language:
            args += [f"-metadata:s:s:{i}", f"language={sub.language}"]
        if sub.title:
            args += [f"-metadata:s:s:{i}", f"title={sub.title}"]
        flags = [
            f
            for f, on in (
                ("default", sub.default),
                ("forced", sub.forced),
                ("hearing_impaired", sub.hearing_impaired),
            )
            if on
        ]
        args += [f"-disposition:s:{i}", "+".join(flags) or "0"]
    args += [f"file:{path}"]
    subprocess.run(args, check=True)  # noqa: S603 - test helper, argument list
    srt.unlink()
    return path
