from typing import Any

import pytest
from fastapi.testclient import TestClient

from reelhaven.db import Database, Library, Profile
from reelhaven.profiles import BUILTIN_PROFILES, ProfileSettings, ensure_builtin_profiles
from tests.helpers import API, admin_client


def test_settings_defaults_and_h264_rule() -> None:
    assert ProfileSettings().codec == "hevc"
    assert ProfileSettings().ten_bit is True
    assert ProfileSettings(codec="h264", ten_bit=True).ten_bit is False


@pytest.mark.parametrize(
    "bad", [{"quality": 0}, {"quality": 11}, {"max_height": 900}, {"codec": "vp9"}, {"crf": 20}]
)
def test_settings_validation(bad: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        ProfileSettings.model_validate(bad)


def test_builtins_created_and_kept_current(db: Database) -> None:
    ensure_builtin_profiles(db)
    ensure_builtin_profiles(db)  # idempotent
    with db.write() as session:
        rows = {p.name: p for p in session.query(Profile)}
        assert set(rows) == set(BUILTIN_PROFILES)
        rows["Balanced"].settings = {**rows["Balanced"].settings, "quality": 1}
    ensure_builtin_profiles(db)  # an upgrade restores the shipped definition
    with db.read() as session:
        balanced = session.query(Profile).filter_by(name="Balanced").one()
        assert balanced.settings["quality"] == BUILTIN_PROFILES["Balanced"].quality


def test_profile_api(client: TestClient) -> None:
    admin = admin_client(client.app)  # type: ignore[arg-type]
    profiles = admin.get(f"{API}/profiles").json()
    assert [p["name"] for p in profiles] == ["Balanced", "High quality", "Small"]
    assert all(p["builtin"] for p in profiles)
    balanced = profiles[0]

    # Built-ins are read-only: copy them instead.
    settings: dict[str, Any] = {**balanced["settings"], "quality": 7, "max_height": 1080}
    body: dict[str, Any] = {"name": "Mine", "settings": settings}
    assert (
        admin.put(f"{API}/profiles/{balanced['id']}", json=body).json()["detail"]
        == "builtin_profile"
    )
    mine = admin.post(f"{API}/profiles", json=body).json()
    assert mine["settings"]["max_height"] == 1080
    assert admin.post(f"{API}/profiles", json=body).status_code == 409

    db: Database = client.app.state.db  # type: ignore[attr-defined]
    with db.write() as session:
        session.add(Library(name="Movies", type="movies", path="/media/Movies"))
    lib_id = 1
    assert admin.get(f"{API}/libraries/{lib_id}/profile").json() == {"profile_id": None}
    assert (
        admin.put(f"{API}/libraries/{lib_id}/profile", json={"profile_id": mine["id"]}).status_code
        == 200
    )
    listed = {p["name"]: p for p in admin.get(f"{API}/profiles").json()}
    assert listed["Mine"]["used_by"] == ["Movies"]
    assert admin.delete(f"{API}/profiles/{mine['id']}").json()["detail"] == "profile_in_use"

    updated = admin.put(
        f"{API}/profiles/{mine['id']}",
        json={**body, "settings": {**settings, "codec": "av1"}},
    )
    assert updated.json()["settings"]["codec"] == "av1"
    admin.put(f"{API}/libraries/{lib_id}/profile", json={"profile_id": None})
    assert admin.delete(f"{API}/profiles/{mine['id']}").status_code == 204
    assert (
        admin.put(f"{API}/libraries/{lib_id}/profile", json={"profile_id": 999}).status_code == 404
    )
