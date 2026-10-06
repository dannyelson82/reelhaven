"""Engine, sessions and migrations."""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def make_engine(url: str) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _sqlite_pragmas)
    return engine


def alembic_config(engine: Engine) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.attributes["engine"] = engine
    return config


class Database:
    """Owns the engine. Reads run concurrently; writes take one process-wide lock."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.engine = make_engine(f"sqlite:///{path}")
        self._factory = sessionmaker(self.engine, expire_on_commit=False)
        self._write_lock = threading.Lock()

    def migrate(self) -> None:
        """Bring the schema up to date. Safe to run on every start."""
        with self._write_lock:
            command.upgrade(alembic_config(self.engine), "head")

    @contextmanager
    def read(self) -> Iterator[Session]:
        with self._factory() as session:
            yield session

    @contextmanager
    def write(self) -> Iterator[Session]:
        """A transaction that commits on success and rolls back on error."""
        with self._write_lock, self._factory() as session, session.begin():
            yield session

    def close(self) -> None:
        self.engine.dispose()
