"""Developer options (ADR-0033): show the report downloads, stored in the settings table."""

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from reelhaven import settings_store

KEY = "developer"


class DeveloperSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Shows Download failure report (Jobs) and Download review report (Review).
    enabled: bool = False


def load(session: Session) -> DeveloperSettings:
    raw = settings_store.get(session, KEY)
    return DeveloperSettings() if raw is None else DeveloperSettings.model_validate(raw)


def save(session: Session, value: DeveloperSettings) -> None:
    settings_store.put(session, KEY, value.model_dump())
