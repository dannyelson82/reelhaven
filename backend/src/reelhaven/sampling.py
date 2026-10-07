"""Which files a test run tries (ADR-0020): a varied sample, largest first."""

from dataclasses import dataclass

MAX_SAMPLES = 5


@dataclass(frozen=True)
class Candidate:
    file_id: int
    size: int
    title_id: int | None  # files of one movie or series share a title
    height: int | None
    hdr: str | None


def _kind(c: Candidate) -> tuple[int, str]:
    height = c.height or 0
    bucket = 2160 if height > 1440 else 1080 if height > 800 else 720 if height > 576 else 480
    return bucket, c.hdr or "sdr"


def choose_samples(candidates: list[Candidate], count: int) -> list[int]:
    """Up to ``count`` file ids: first one per kind of video (resolution and HDR),
    then one per title, then the largest of the rest. Big files come first in
    each pass because they show the most savings and stress the encoder most."""
    ordered = sorted(candidates, key=lambda c: (-c.size, c.file_id))
    chosen: list[Candidate] = []

    def take(pick: Candidate) -> None:
        if len(chosen) < count and pick not in chosen:
            chosen.append(pick)

    kinds: set[tuple[int, str]] = set()
    for c in ordered:
        if _kind(c) not in kinds:
            kinds.add(_kind(c))
            take(c)
    titles = {c.title_id for c in chosen}
    for c in ordered:
        if c.title_id is None or c.title_id not in titles:
            titles.add(c.title_id)
            take(c)
    for c in ordered:
        take(c)
    return [c.file_id for c in chosen]
