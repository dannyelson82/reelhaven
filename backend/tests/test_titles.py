import pytest

from reelhaven.titles import comparable_title, parse_folder, title_folder


@pytest.mark.parametrize(
    ("path", "kind", "folder"),
    [
        ("Breaking Bad/Season 1/S01E01.mkv", "tv", "Breaking Bad"),
        ("Breaking Bad/S01E01.mkv", "tv", "Breaking Bad"),
        ("Amélie (2001)/Amélie.mkv", "movies", "Amélie (2001)"),
        ("Collections/Alien (1979)/Alien.mkv", "movies", "Collections/Alien (1979)"),
        ("Planet Earth (2006)/Season 01/e1.mkv", "other", "Planet Earth (2006)"),
        ("loose movie.mkv", "movies", "loose movie"),
    ],
)
def test_title_folder(path: str, kind: str, folder: str) -> None:
    assert title_folder(path, kind) == folder


def test_parse_folder() -> None:
    info = parse_folder("Amélie (2001) {tmdb-194} [imdbid-tt0211915]")
    assert (info.name, info.year, info.tmdb, info.imdb) == ("Amélie", 2001, "194", "tt0211915")
    assert parse_folder("The.Matrix.1999").name == "The Matrix 1999"
    assert parse_folder("Dark [tvdbid-334824]").tvdb == "334824"
    assert parse_folder("Collections/Alien (1979)").name == "Alien"
    assert parse_folder("Show").year is None


def test_comparable_title() -> None:
    assert comparable_title("Amélie") == comparable_title("amelie")
    assert comparable_title("The Office") == comparable_title("Office")
    assert comparable_title("Fast & Furious") == comparable_title("Fast and Furious")
    assert comparable_title("Alien") != comparable_title("Aliens")
