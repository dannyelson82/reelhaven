"""How long originals stay in the recycle bin, including not at all (ADR-0028)."""

from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from reelhaven.config import Settings
from reelhaven.db import AuditLog, Database, JobResult, RecycleItem
from tests.helpers import API
from tests.test_remux import MULTI, app, apply_all, setup_library  # noqa: F401 - shared fixture

FILM = {"Film (2020)/film.mkv": MULTI}


def keep(admin: TestClient, days: int) -> None:
    response = admin.put(f"{API}/settings/recycle", json={"keep_days": days})
    assert response.status_code == 200, response.text


def items(db: Database) -> list[RecycleItem]:
    with db.read() as session:
        return list(session.scalars(select(RecycleItem).order_by(RecycleItem.id)))


def test_setting_defaults_validates_and_is_audited(
    app: FastAPI,  # noqa: F811
    settings: Settings,
) -> None:
    admin, _lib, _root = setup_library(app, settings, FILM)
    assert admin.get(f"{API}/settings/recycle").json() == {"keep_days": 14}
    keep(admin, 0)
    assert admin.get(f"{API}/settings/recycle").json() == {"keep_days": 0}
    for bad in ({"keep_days": 5}, {"keep_days": -1}, {"keep_days": 14, "extra": 1}):
        assert admin.put(f"{API}/settings/recycle", json=bad).status_code == 422
    keep(admin, 0)  # unchanged: no second audit entry
    with app.state.db.read() as session:
        logged = session.scalars(
            select(AuditLog).where(AuditLog.action == "recycle.settings_changed")
        ).all()
    assert [entry.detail for entry in logged] == [{"keep_days": 0, "before": 14}]


def test_originals_are_kept_for_the_chosen_days(
    app: FastAPI,  # noqa: F811
    settings: Settings,
) -> None:
    admin, lib, _root = setup_library(app, settings, FILM)
    keep(admin, 3)
    apply_all(app, admin, lib)
    (item,) = items(app.state.db)
    assert item.expires_at - item.created_at == timedelta(days=3)
    assert Path(item.stored_path).exists()


def test_bin_off_deletes_the_original_after_verification(
    app: FastAPI,  # noqa: F811
    settings: Settings,
) -> None:
    admin, lib, root = setup_library(app, settings, FILM)
    keep(admin, 0)
    assert apply_all(app, admin, lib) == {"queued": 1, "waiting": 0}
    db: Database = app.state.db
    (item,) = items(db)
    assert item.purged_at is not None
    assert not Path(item.stored_path).exists()
    assert not (root / ".reelhaven" / "recycle" / "job-1").exists()  # no empty folders left
    assert (root / "Film (2020)" / "film.mkv").exists()  # the verified replacement
    assert admin.get(f"{API}/recycle").json() == []
    with db.read() as session:
        result = session.scalars(select(JobResult)).one()
        skipped = session.scalars(select(AuditLog).where(AuditLog.action == "recycle.skipped"))
        assert result.outcome == "replaced"  # still counts as space saved
        assert len(skipped.all()) == 1


def test_turning_the_bin_off_keeps_existing_items_and_restores_still_work(
    app: FastAPI,  # noqa: F811
    settings: Settings,
) -> None:
    admin, lib, root = setup_library(app, settings, FILM)
    apply_all(app, admin, lib)  # kept for 14 days
    keep(admin, 0)
    db: Database = app.state.db
    (item,) = items(db)
    assert item.purged_at is None and Path(item.stored_path).exists()

    # Restoring the original swaps out ReelHaven's version, which isn't kept either.
    assert admin.post(f"{API}/recycle/{item.id}/restore").status_code == 200
    _first, swap = items(db)
    assert swap.reason == "restore-swap"
    assert swap.purged_at is not None
    assert not Path(swap.stored_path).exists()
    assert (root / "Film (2020)" / "film.mkv").exists()  # the original, back in place
