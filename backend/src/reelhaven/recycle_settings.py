"""How long replaced originals stay in the recycle bin (ADR-0028), stored in the settings table."""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from reelhaven import settings_store
from reelhaven.db import Database

KEY = "recycle"
KeepDays = Literal[0, 1, 3, 7, 14, 30]


class RecycleSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 0: no recycle bin; an original is deleted once its replacement is verified.
    keep_days: KeepDays = 14


def load(session: Session) -> RecycleSettings:
    raw = settings_store.get(session, KEY)
    return RecycleSettings() if raw is None else RecycleSettings.model_validate(raw)


def save(session: Session, value: RecycleSettings) -> None:
    settings_store.put(session, KEY, value.model_dump())


def keep_days(db: Database) -> int:
    with db.read() as session:
        return load(session).keep_days
