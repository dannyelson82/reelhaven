"""Test films (ADR-0031): open-licence films to try settings on, downloaded only on request.

Downloads come only from the fixed HTTPS addresses below, with TLS verified, and are kept
only when their SHA-256 matches. They live in appdata (``<config>/films``) and can be
deleted at any time.
"""

import hashlib
import logging
import shutil
import threading
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

CHUNK = 1 << 20
TIMEOUT = httpx.Timeout(30.0, read=120.0)


@dataclass(frozen=True)
class Film:
    id: str
    title: str
    year: int
    # What it's good for testing, in plain words.
    about: str
    width: int
    height: int
    hdr: bool
    minutes: int
    url: str
    download_bytes: int
    sha256: str
    # A zip holding the film: the name of the one file inside to keep.
    member: str | None
    credit: str
    licence: str
    licence_url: str
    source_url: str

    @property
    def filename(self) -> str:
        return self.member or self.url.rsplit("/", 1)[-1]


_BLENDER = "https://download.blender.org"
_NETFLIX = "https://download.opencontent.netflix.com.s3.amazonaws.com"
_CC_BY_3 = ("CC BY 3.0", "https://creativecommons.org/licenses/by/3.0/")
_CC_BY_4 = ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/")

CATALOGUE: tuple[Film, ...] = (
    Film(
        id="big-buck-bunny-1080p",
        title="Big Buck Bunny",
        year=2008,
        about="Bright, colourful animation with fine fur and grass. Easy to compress.",
        width=1920,
        height=1080,
        hdr=False,
        minutes=10,
        url=f"{_BLENDER}/demo/movies/BBB/bbb_sunflower_1080p_30fps_normal.mp4.zip",
        download_bytes=275_524_128,
        sha256="e320fef389ec749117d0c1583945039266a40f25483881c2ff0d33207e62b362",
        member="bbb_sunflower_1080p_30fps_normal.mp4",
        credit="(c) copyright 2008, Blender Foundation / www.bigbuckbunny.org",
        licence=_CC_BY_3[0],
        licence_url=_CC_BY_3[1],
        source_url="https://peach.blender.org/",
    ),
    Film(
        id="big-buck-bunny-4k",
        title="Big Buck Bunny (4K)",
        year=2008,
        about="The same animation in 4K: for trying 4K settings and speeds.",
        width=3840,
        height=2160,
        hdr=False,
        minutes=10,
        url=f"{_BLENDER}/demo/movies/BBB/bbb_sunflower_2160p_30fps_normal.mp4.zip",
        download_bytes=632_204_510,
        sha256="750b255c6d9fee1e2a03a6716d4f358bca56e9115bf3e06a66162fc5272ae151",
        member="bbb_sunflower_2160p_30fps_normal.mp4",
        credit="(c) copyright 2008, Blender Foundation / www.bigbuckbunny.org",
        licence=_CC_BY_3[0],
        licence_url=_CC_BY_3[1],
        source_url="https://peach.blender.org/",
    ),
    Film(
        id="sintel-1080p",
        title="Sintel",
        year=2010,
        about="Darker animation with snow, smoke and fast action, where banding and blocks show.",
        width=1920,
        height=818,
        hdr=False,
        minutes=15,
        url=f"{_BLENDER}/durian/movies/Sintel.2010.1080p.mkv",
        download_bytes=1_180_090_590,
        sha256="97f1dbc66231df42ad49bd8c29aa174b8f48933058e47e7157d4ba63d93a8efa",
        member=None,
        credit="(c) copyright Blender Foundation | durian.blender.org",
        licence=_CC_BY_3[0],
        licence_url=_CC_BY_3[1],
        source_url="https://durian.blender.org/",
    ),
    Film(
        id="tears-of-steel-1080p",
        title="Tears of Steel",
        year=2012,
        about="Live action with visual effects, faces and dark scenes.",
        width=1920,
        height=800,
        hdr=False,
        minutes=12,
        url=f"{_BLENDER}/demo/movies/ToS/ToS-4k-1920.mov.zip",
        download_bytes=738_876_511,
        sha256="58f2dd086aeefe110b10a6d9d7529faa68cf6ec3035eb2410036b1e7896f426a",
        member="ToS-4k-1920.mov",
        credit="(CC) Blender Foundation | mango.blender.org",
        licence=_CC_BY_3[0],
        licence_url=_CC_BY_3[1],
        source_url="https://mango.blender.org/",
    ),
)

FilmState = Literal["available", "downloading", "verifying", "ready", "failed"]


@dataclass
class _Progress:
    state: FilmState = "downloading"
    done: int = 0
    error: str | None = None
    cancel: threading.Event = field(default_factory=threading.Event)


class FilmError(ValueError):
    """A request that can't be done; the message is the API's error code."""


def film(film_id: str) -> Film:
    for item in CATALOGUE:
        if item.id == film_id:
            return item
    raise FilmError("film_not_found")


class FilmLibrary:
    """The downloaded films, and downloads in progress (one thread each)."""

    def __init__(self, folder: Path, transport: httpx.BaseTransport | None = None) -> None:
        self.folder = folder
        self._transport = transport  # tests serve downloads without the internet
        self._lock = threading.Lock()
        self._progress: dict[str, _Progress] = {}

    def path(self, item: Film) -> Path:
        """Where a downloaded film lives: its own folder, named by its id."""
        return self.folder / item.id / item.filename

    def state(self, item: Film) -> tuple[FilmState, int, str | None]:
        """(state, bytes downloaded so far, error)."""
        with self._lock:
            progress = self._progress.get(item.id)
            if progress is not None and progress.state != "ready":
                return progress.state, progress.done, progress.error
        if self.path(item).is_file():
            return "ready", item.download_bytes, None
        return "available", 0, None

    def download(self, item: Film) -> None:
        with self._lock:
            current = self._progress.get(item.id)
            if current is not None and current.state in ("downloading", "verifying"):
                raise FilmError("already_downloading")
            if self.path(item).is_file():
                raise FilmError("already_downloaded")
            progress = _Progress()
            self._progress[item.id] = progress
        threading.Thread(
            target=self._run, args=(item, progress), name=f"film-{item.id}", daemon=True
        ).start()

    def delete(self, item: Film) -> None:
        """Stop a download, or remove a downloaded film."""
        with self._lock:
            progress = self._progress.pop(item.id, None)
        if progress is not None:
            progress.cancel.set()
        shutil.rmtree(self.folder / item.id, ignore_errors=True)

    def wait(self, item: Film, timeout: float) -> FilmState:
        """For tests: wait until a download has finished either way."""
        thread = next((t for t in threading.enumerate() if t.name == f"film-{item.id}"), None)
        if thread is not None:
            thread.join(timeout)
        return self.state(item)[0]

    def _run(self, item: Film, progress: _Progress) -> None:
        target = self.folder / item.id
        part = target / f"{item.id}.part"
        try:
            target.mkdir(parents=True, exist_ok=True)
            digest = self._fetch(item, part, progress)
            if progress.cancel.is_set():
                return
            progress.state = "verifying"
            if digest != item.sha256:
                raise FilmError("The download was damaged (checksum mismatch). Try again.")
            if item.member is not None:
                _extract(part, item.member, self.path(item))
                part.unlink()
            else:
                part.rename(self.path(item))
            progress.state = "ready"
        except Exception as exc:
            logger.warning("film download failed", extra={"film": item.id, "error": str(exc)})
            shutil.rmtree(target, ignore_errors=True)
            progress.state, progress.error = "failed", str(exc) or exc.__class__.__name__
        finally:
            if progress.cancel.is_set():
                shutil.rmtree(target, ignore_errors=True)

    def _fetch(self, item: Film, part: Path, progress: _Progress) -> str:
        digest = hashlib.sha256()
        with (
            httpx.Client(
                transport=self._transport, timeout=TIMEOUT, follow_redirects=True
            ) as client,
            client.stream("GET", item.url) as response,
            part.open("wb") as out,
        ):
            response.raise_for_status()
            if response.url.scheme != "https":  # a redirect must not downgrade the download
                raise FilmError("The download was redirected to an insecure address.")
            for chunk in response.iter_bytes(CHUNK):
                if progress.cancel.is_set():
                    break
                out.write(chunk)
                digest.update(chunk)
                progress.done += len(chunk)
        return digest.hexdigest()


def _extract(archive: Path, member: str, output: Path) -> None:
    """Copy the one expected file out of a zip, whatever else it holds; nothing else is
    written, so names inside the archive can't reach other folders."""
    with zipfile.ZipFile(archive) as zipped, zipped.open(member) as source:
        partial = output.with_suffix(output.suffix + ".part")
        with partial.open("wb") as out:
            shutil.copyfileobj(source, out, CHUNK)
        partial.rename(output)
