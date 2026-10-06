"""Language code normalisation (ADR-0017).

Files, Sonarr/Radarr and TMDB describe languages differently: ``fre``,
``fra``, ``fr`` or "French". Everything is normalised to one canonical
ISO 639-3 / 639-2/T code (``fra``) before any comparison.
"""

import re
from functools import lru_cache

import pycountry

_LANGUAGE_TAG = re.compile(r"^([a-z]{2,3})-(?:[a-z]{2}|[a-z]{4}|\d{3})$")

# Codes meaning "no particular language": treated as untagged.
UNTAGGED = frozenset({"", "und", "zxx", "mis", "mul", "unk", "unknown", "none", "any"})

# Names used by Sonarr/Radarr (and some tagging tools) that ISO doesn't use.
_ALIASES = {
    "portuguese (brazil)": "por",
    "brazilian": "por",
    "brazilian portuguese": "por",
    "spanish (latino)": "spa",
    "latino": "spa",
    "flemish": "nld",
    "chinese": "zho",
    "mandarin": "zho",
    "cantonese": "yue",
    "persian": "fas",
    "farsi": "fas",
    "greek": "ell",
    "modern greek": "ell",
    "norwegian": "nor",
    "bokmal": "nob",
    "norwegian bokmal": "nob",
    "tagalog": "tgl",
    "filipino": "fil",
    "original": "",
}


@lru_cache(maxsize=1024)
def normalise(code: str | None) -> str | None:
    """Canonical 3-letter code, or None for untagged/unknown-language markers.

    Unrecognised values are returned lower-cased so they still compare equal
    to themselves.
    """
    if code is None:
        return None
    value = code.strip().lower().replace("_", "-")
    if value in UNTAGGED:
        return None
    # "en-US", "pt-BR", "zh-Hant", "es-419": region/script don't matter here.
    tagged = _LANGUAGE_TAG.match(value)
    base = tagged.group(1) if tagged else value
    if base in _ALIASES:
        return _ALIASES[base] or None
    if value in _ALIASES:
        return _ALIASES[value] or None
    language = None
    if len(base) == 2:
        language = pycountry.languages.get(alpha_2=base)
    elif len(base) == 3:
        language = pycountry.languages.get(alpha_3=base) or pycountry.languages.get(
            bibliographic=base
        )
    if language is None:
        try:
            language = pycountry.languages.lookup(value)
        except LookupError:
            return value
    canonical: str = language.alpha_3
    return canonical


@lru_cache(maxsize=1024)
def display_name(code: str | None) -> str:
    """Human-readable name for a canonical code ("fra" -> "French")."""
    if code is None:
        return "Untagged"
    language = pycountry.languages.get(alpha_3=code)
    return language.name if language is not None else code
