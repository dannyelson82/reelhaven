import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, StatementError

from reelhaven import audit, settings_store
from reelhaven.db import AuditLog, AuthSession, Base, Database, User


def test_migrations_match_models(db: Database) -> None:
    with db.engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_migrate_is_idempotent(db: Database) -> None:
    db.migrate()
    db.migrate()


def test_sqlite_pragmas(db: Database) -> None:
    with db.read() as session:
        assert session.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert session.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_datetimes_round_trip_as_utc(db: Database) -> None:
    created = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    with db.write() as session:
        session.add(User(username="a", password_hash="x", created_at=created))
    with db.read() as session:
        user = session.scalars(select(User)).one()
        assert user.created_at == created
        assert user.created_at.tzinfo is UTC


def test_naive_datetimes_rejected(db: Database) -> None:
    with pytest.raises(StatementError, match="naive"), db.write() as session:
        session.add(
            User(username="a", password_hash="x", created_at=datetime(2026, 1, 1))  # noqa: DTZ001
        )
        session.flush()


def test_write_rolls_back_on_error(db: Database) -> None:
    with pytest.raises(RuntimeError), db.write() as session:
        session.add(User(username="a", password_hash="x"))
        session.flush()
        raise RuntimeError("boom")
    with db.read() as session:
        assert session.scalars(select(User)).all() == []


def test_usernames_unique(db: Database) -> None:
    with db.write() as session:
        session.add(User(username="a", password_hash="x"))
    with pytest.raises(IntegrityError), db.write() as session:
        session.add(User(username="a", password_hash="y"))


def test_deleting_user_deletes_sessions(db: Database) -> None:
    with db.write() as session:
        user = User(username="a", password_hash="x")
        session.add(user)
        session.flush()
        session.add(
            AuthSession(
                id_hash="h" * 64, user_id=user.id, expires_at=datetime.now(UTC) + timedelta(days=1)
            )
        )
    with db.write() as session:
        session.execute(text("DELETE FROM users"))
    with db.read() as session:
        assert session.scalars(select(AuthSession)).all() == []


def test_audit_record(db: Database) -> None:
    with db.write() as session:
        audit.record(session, "admin", "login.failed", "admin", {"ip": "10.0.0.5"})
    with db.read() as session:
        entry = session.scalars(select(AuditLog)).one()
        assert (entry.actor, entry.action, entry.detail) == (
            "admin",
            "login.failed",
            {"ip": "10.0.0.5"},
        )


def test_settings_store(db: Database) -> None:
    with db.write() as session:
        assert settings_store.get(session, "k") is None
        settings_store.put(session, "k", {"a": 1})
    with db.write() as session:
        settings_store.put(session, "k", {"a": 2})
    with db.read() as session:
        assert settings_store.get(session, "k") == {"a": 2}


def test_concurrent_writes_are_serialised(db: Database) -> None:
    errors: list[Exception] = []

    def writer(n: int) -> None:
        try:
            for i in range(20):
                with db.write() as session:
                    audit.record(session, f"t{n}", "test", str(i))
        except Exception as exc:  # pragma: no cover - only on failure
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    with db.read() as session:
        assert len(session.scalars(select(AuditLog)).all()) == 100


def test_app_startup_creates_database(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from reelhaven.app import create_app
    from reelhaven.config import Settings

    settings = Settings(config_dir=tmp_path / "cfg")
    with TestClient(create_app(settings)):
        pass
    assert (tmp_path / "cfg" / "reelhaven.db").is_file()
