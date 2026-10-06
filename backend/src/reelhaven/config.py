"""Process settings, read from environment variables.

User-editable settings live in the database (``settings`` table); this module
only covers what must be known before the database is opened.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["debug", "info", "warning", "error"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REELHAVEN_", extra="ignore")

    # The container sets REELHAVEN_CONFIG_DIR=/config. The development default
    # is deliberately a local folder: in code-server, /config is the home dir.
    config_dir: Path = Path(".dev-config")
    web_dir: Path | None = None
    # Root of all libraries. The container maps media here; in development
    # point it at /projects/reelhaven-testmedia.
    media_root: Path = Path("/media")
    # Encoder binaries (jellyfin-ffmpeg in the container; any ffmpeg in dev).
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    probe_timeout_s: float = Field(default=120, gt=0)
    host: str = "0.0.0.0"  # noqa: S104 - a container must listen on all interfaces
    port: int = Field(default=7171, ge=1, le=65535)
    log_level: LogLevel = "info"
    log_file_max_bytes: int = 10 * 1024 * 1024
    log_file_backups: int = 5

    @property
    def log_dir(self) -> Path:
        return self.config_dir / "logs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
