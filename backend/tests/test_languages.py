import pytest

from reelhaven.media.languages import display_name, normalise


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("eng", "eng"),
        ("en", "eng"),
        ("EN", "eng"),
        ("English", "eng"),
        ("fre", "fra"),
        ("fra", "fra"),
        ("fr", "fra"),
        ("French", "fra"),
        ("ger", "deu"),
        ("deu", "deu"),
        ("German", "deu"),
        ("chi", "zho"),
        ("Chinese", "zho"),
        ("jpn", "jpn"),
        ("ja", "jpn"),
        ("Japanese", "jpn"),
        ("pt-BR", "por"),
        ("Portuguese (Brazil)", "por"),
        ("en-US", "eng"),
        ("Spanish (Latino)", "spa"),
        ("Flemish", "nld"),
        ("Persian", "fas"),
        ("Greek", "ell"),
    ],
)
def test_normalise(raw: str, expected: str) -> None:
    assert normalise(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "und", "UND", "zxx", "mis", "mul", " und ", "Unknown"])
def test_untagged(raw: str | None) -> None:
    assert normalise(raw) is None


def test_unknown_values_kept_lowercase() -> None:
    assert normalise("Klingon-ish") == "klingon-ish"


def test_display_name() -> None:
    assert display_name("fra") == "French"
    assert display_name(None) == "Untagged"
    assert display_name("xyz123") == "xyz123"
