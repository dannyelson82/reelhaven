"""Compression profiles (ARCHITECTURE.md §7.1, ADR-0019)."""

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from reelhaven.db import Database

Speed = Literal["fast", "balanced", "slow"]
AudioMode = Literal["copy", "compress_lossless"]


class ProfileSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codec: Literal["hevc", "av1", "h264"] = "hevc"
    # Normalised quality: 1 = smallest files, 10 = closest to the source.
    quality: int = Field(default=6, ge=1, le=10)
    speed: Speed = "balanced"
    ten_bit: bool = True
    # Cap the height (never upscales); None keeps the source resolution.
    max_height: Literal[2160, 1440, 1080, 720] | None = None
    # Lossless audio (TrueHD without Atmos, DTS-HD MA, FLAC, PCM) to E-AC-3.
    audio: AudioMode = "copy"
    add_stereo_aac: bool = False
    # Results saving less than this are discarded and the file marked "no gain".
    min_savings_percent: int = Field(default=10, ge=0, le=90)

    @model_validator(mode="after")
    def _h264_is_8_bit(self) -> "ProfileSettings":
        if self.codec == "h264":
            self.ten_bit = False  # 10-bit H.264 barely plays anywhere
        return self


BUILTIN_PROFILES: dict[str, ProfileSettings] = {
    "High quality": ProfileSettings(quality=8, speed="slow"),
    "Balanced": ProfileSettings(quality=6),
    "Small": ProfileSettings(quality=4, speed="balanced"),
}


def ensure_builtin_profiles(db: "Database") -> None:
    """Create the built-in profiles, and keep their settings current after upgrades."""
    from sqlalchemy import select

    from reelhaven.db import Profile

    with db.write() as session:
        existing = {
            p.name: p for p in session.scalars(select(Profile).where(Profile.builtin.is_(True)))
        }
        for name, settings in BUILTIN_PROFILES.items():
            row = existing.get(name)
            if row is None:
                session.add(Profile(name=name, builtin=True, settings=settings.model_dump()))
            elif row.settings != settings.model_dump():
                row.settings = settings.model_dump()
