import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, StatementError

from reelhaven import audit, settings_store
from reelhaven.db import AuditLog, AuthSession, Base, Database, Library, User


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


def test_upgrade_with_existing_library(tmp_path: Path) -> None:
    """Columns added later get sensible values for rows that already exist."""
    from alembic import command

    from reelhaven.db.engine import alembic_config

    database = Database(tmp_path / "old.db")
    config = alembic_config(database.engine)
    command.upgrade(config, "0005")
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO libraries (name, type, path, created_at, updated_at) "
                "VALUES ('Old', 'movies', '/media/Old', '2026-01-01', '2026-01-01')"
            )
        )
    database.migrate()
    with database.read() as session:
        library = session.scalars(select(Library)).one()
        assert library.language_policy == {}
    database.close()


def test_upgrade_clears_failures_that_cant_be_retried(tmp_path: Path) -> None:
    """0023: failed jobs whose file has had a newer job, or whose file is gone."""
    from alembic import command

    from reelhaven.db import Job, MediaFile
    from reelhaven.db.engine import alembic_config

    database = Database(tmp_path / "old.db")
    command.upgrade(alembic_config(database.engine), "0022")
    with database.write() as session:
        library = Library(name="TV", type="tv", path="/media/TV")
        session.add(library)
        session.flush()
        files = [
            MediaFile(
                library_id=library.id,
                path=f"/media/TV/{n}.mkv",
                relative_path=f"{n}.mkv",
                size=1,
                mtime_ns=1,
                fingerprint=n,
                status="ok",
            )
            for n in ("a", "b")
        ]
        session.add_all(files)
        session.flush()

        def job(file_id: int | None, status: str, kind: str = "encode") -> Job:
            row = Job(
                library_id=library.id,
                media_file_id=file_id,
                type=kind,
                status=status,
                source_path="/media/TV/x.mkv",
                source_size=1,
                source_mtime_ns=1,
                plan={},
                probe={},
                requested_by="automatic",
            )
            session.add(row)
            session.flush()
            return row

        superseded = job(files[0].id, "failed")
        job(files[0].id, "done")
        latest = job(files[1].id, "failed")  # still the file's latest: Retry all handles it
        gone = job(None, "failed")
        film_step = job(None, "failed", "tune")  # sweet-spot steps have no library file
        ids = (superseded.id, latest.id, gone.id, film_step.id)
    database.migrate()
    with database.read() as session:
        cleared = {
            j.id: j.cleared_at is not None for j in session.scalars(select(Job)) if j.id in ids
        }
    assert cleared == {
        superseded.id: True,
        latest.id: False,
        gone.id: True,
        film_step.id: False,
    }
    database.close()
