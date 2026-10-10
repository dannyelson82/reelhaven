"""User settings for encode devices (stored in the settings table)."""

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from reelhaven import settings_store

KEY = "devices"


class DeviceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    # Consumer NVIDIA cards limit simultaneous encode sessions; 2 is safe everywhere.
    concurrency: int = Field(default=2, ge=1, le=8)


class DeviceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpu_enabled: bool = False  # CPU encoding is slow; off unless asked for (ADR-0019)
    cpu_concurrency: int = Field(default=1, ge=1, le=4)
    devices: dict[str, DeviceConfig] = Field(default_factory=dict)
    # CPU limiter: at most this many CPU cores for everything ReelHaven runs (ffmpeg,
    # ffprobe); None uses all of them. Always at low priority either way (cpu_limit.py).
    cpu_cores: int | None = Field(default=None, ge=1, le=1024)

    def config_for(self, device_id: str) -> DeviceConfig:
        return self.devices.get(device_id, DeviceConfig())


def load(session: Session) -> DeviceSettings:
    raw = settings_store.get(session, KEY)
    return DeviceSettings() if raw is None else DeviceSettings.model_validate(raw)


def save(session: Session, value: DeviceSettings) -> None:
    settings_store.put(session, KEY, value.model_dump())
