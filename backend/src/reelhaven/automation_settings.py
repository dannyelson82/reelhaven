"""Automation settings (ADR-0025), stored in the settings table."""

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from reelhaven import settings_store
from reelhaven.db import Database

KEY = "automation"


class AutomationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paused: bool = False  # no new job starts, manual or automatic; running ones finish
    rescan_enabled: bool = True
    rescan_at: str = Field(default="03:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


def load(session: Session) -> AutomationSettings:
    raw = settings_store.get(session, KEY)
    return AutomationSettings() if raw is None else AutomationSettings.model_validate(raw)


def save(session: Session, value: AutomationSettings) -> None:
    settings_store.put(session, KEY, value.model_dump())


def is_paused(db: Database) -> bool:
    with db.read() as session:
        return load(session).paused
