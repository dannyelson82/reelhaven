from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reelhaven.app import create_app
from reelhaven.config import Settings
from reelhaven.db import Database


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(config_dir=tmp_path / "config")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings, gateways=frozenset())
    with TestClient(app) as test_client:  # runs startup (migrations)
        yield test_client


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(tmp_path / "test.db")
    database.migrate()
    yield database
    database.close()
