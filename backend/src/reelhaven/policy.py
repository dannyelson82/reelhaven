"""Per-library language policy (ARCHITECTURE.md §8.1)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from reelhaven.media.languages import normalise


class LanguagePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Languages to keep besides the original. The first one is the viewer's
    # own language: it decides which subtitle becomes the default.
    keep_languages: list[str] = Field(default_factory=lambda: ["eng"], min_length=1, max_length=20)
    keep_original: bool = True
    keep_subtitles_full: bool = True
    keep_subtitles_forced: bool = True
    keep_subtitles_sdh: bool = True
    keep_commentary: bool = True
    # Mark the subtitle chosen as default in the viewer's language as forced, so players show
    # it automatically: forced subtitles for foreign lines, or full ones for foreign audio.
    force_subtitles: bool = True
    # "keep", or a language code untagged tracks should be treated as (ADR-0017).
    untagged: str = "keep"
    set_defaults: bool = True
    # ADR-0032: flag for review, or (automatic libraries) quarantine or delete and ask
    # Sonarr/Radarr for another release.
    wrong_language_action: Literal["flag", "quarantine", "delete"] = "flag"

    @field_validator("keep_languages")
    @classmethod
    def _languages(cls, values: list[str]) -> list[str]:
        out: list[str] = []
        for value in values:
            code = normalise(value)
            if code is None:
                raise ValueError(f"not a language: {value!r}")
            if code not in out:
                out.append(code)
        return out

    @field_validator("untagged")
    @classmethod
    def _untagged(cls, value: str) -> str:
        if value == "keep":
            return value
        code = normalise(value)
        if code is None:
            raise ValueError("use 'keep' or a language")
        return code

    @property
    def viewer_language(self) -> str:
        return self.keep_languages[0]
