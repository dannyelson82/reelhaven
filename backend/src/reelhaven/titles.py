"""Which title (movie or series) a file belongs to, and what its folder says.

Pure functions; no I/O.
"""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath

_YEAR = re.compile(r"[\(\[]((?:19|20)\d{2})[\)\]]")
_IDS = {
    "tmdb": re.compile(r"[\{\[]tmdb(?:id)?[-=](\d+)[\}\]]", re.IGNORECASE),
    "imdb": re.compile(r"[\{\[]imdb(?:id)?[-=](tt\d+)[\}\]]", re.IGNORECASE),
    "tvdb": re.compile(r"[\{\[]tvdb(?:id)?[-=](\d+)[\}\]]", re.IGNORECASE),
}
_BRACKETED = re.compile(r"[\{\[][^\}\]]*[\}\]]")
_SEASON_FOLDER = re.compile(r"^(season|series|staffel|saison)\s*\d+$|^specials$", re.IGNORECASE)


def title_folder(relative_path: str, library_type: str) -> str:
    """The folder that identifies a file's title, relative to the library root.

    TV: the first folder (the series). Movies and other: the folder holding
    the file, skipping a trailing season-style folder. Files directly in the
    root are identified by their own name.
    """
    path = PurePosixPath(relative_path)
    parts = path.parts
    if len(parts) == 1:
        return path.stem  # loose file: its name is the title
    if library_type == "tv":
        return parts[0]
    parent = path.parent
    if _SEASON_FOLDER.match(parent.name) and len(parent.parts) > 1:
        parent = parent.parent
    return parent.as_posix()


@dataclass(frozen=True)
class FolderInfo:
    name: str
    year: int | None
    tmdb: str | None
    imdb: str | None
    tvdb: str | None


def parse_folder(folder: str) -> FolderInfo:
    """Name, year and IDs from a folder like "Amélie (2001) {tmdb-194}"."""
    leaf = PurePosixPath(folder).name or folder
    ids = {key: (m.group(1) if (m := rx.search(leaf)) else None) for key, rx in _IDS.items()}
    year_match = _YEAR.search(leaf)
    name = _BRACKETED.sub("", leaf)
    if year_match:
        name = name[: year_match.start()] if year_match.start() > 0 else name
        name = _YEAR.sub("", name)
    name = re.sub(r"[._]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" -")
    return FolderInfo(
        name=name or leaf,
        year=int(year_match.group(1)) if year_match else None,
        tmdb=ids["tmdb"],
        imdb=ids["imdb"],
        tvdb=ids["tvdb"],
    )


def comparable_title(title: str) -> str:
    """Lower-case, accents and punctuation removed: "Amélie!" == "amelie"."""
    text = unicodedata.normalize("NFKD", title)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"&", " and ", text.lower())
    text = re.sub(r"^(the|a|an) ", "", text)
    return re.sub(r"[^a-z0-9]+", "", text)
