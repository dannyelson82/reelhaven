import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from reelhaven.app import create_app
from reelhaven.config import Settings
from reelhaven.paths import PathNotAllowedError, resolve_within
from tests.helpers import API, admin_client


@pytest.fixture
def media(settings: Settings) -> Path:
    root = settings.media_root
    for folder in ("Movies/Action", "Movies/Drama", "TV/Show A", "Other", ".hidden"):
        (root / folder).mkdir(parents=True)
    (root / "Movies" / "film.mkv").write_bytes(b"x")
    return root


@pytest.fixture
def app(settings: Settings, media: Path) -> Iterator[FastAPI]:
    application = create_app(settings, gateways=frozenset())
    with TestClient(application):
        yield application


@pytest.fixture
def admin(app: FastAPI) -> TestClient:
    return admin_client(app)


# --- resolve_within -------------------------------------------------------------


def test_resolve_relative_and_absolute(media: Path) -> None:
    assert resolve_within(media, "Movies") == media.resolve() / "Movies"
    assert resolve_within(media, str(media / "TV")) == media.resolve() / "TV"
    assert resolve_within(media, "") == media.resolve()


@pytest.mark.parametrize(
    "bad",
    ["..", "../..", "Movies/../../etc", "/etc", "/", "missing", "Movies/\x00x"],
)
def test_resolve_rejects_escapes(media: Path, bad: str) -> None:
    with pytest.raises(PathNotAllowedError):
        resolve_within(media, bad)


def test_resolve_rejects_symlink_escape(media: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (media / "sneaky").symlink_to(outside)
    with pytest.raises(PathNotAllowedError):
        resolve_within(media, "sneaky")


def test_resolve_allows_symlink_inside(media: Path) -> None:
    (media / "alias").symlink_to(media / "Movies")
    assert resolve_within(media, "alias") == media.resolve() / "Movies"


def test_resolve_rejects_internal_folder(media: Path) -> None:
    (media / "Movies" / ".reelhaven" / "recycle").mkdir(parents=True)
    with pytest.raises(PathNotAllowedError):
        resolve_within(media, "Movies/.reelhaven/recycle")


# --- browse --------------------------------------------------------------------


def test_browse_root_lists_visible_folders_only(admin: TestClient) -> None:
    result = admin.get(f"{API}/browse").json()
    assert result["path"] == ""
    assert result["parent"] is None
    assert [d["name"] for d in result["dirs"]] == ["Movies", "Other", "TV"]


def test_browse_subfolder(admin: TestClient) -> None:
    result = admin.get(f"{API}/browse", params={"path": "Movies"}).json()
    assert result["parent"] == ""
    assert result["dirs"] == [
        {"name": "Action", "path": "Movies/Action"},
        {"name": "Drama", "path": "Movies/Drama"},
    ]


def test_browse_hides_symlinks_that_escape(admin: TestClient, media: Path, tmp_path: Path) -> None:
    outside = tmp_path / "secret"
    outside.mkdir()
    (media / "Movies" / "escape").symlink_to(outside)
    names = [
        d["name"] for d in admin.get(f"{API}/browse", params={"path": "Movies"}).json()["dirs"]
    ]
    assert "escape" not in names


@pytest.mark.parametrize("path", ["..", "/etc", "Movies/film.mkv"])
def test_browse_rejects_bad_paths(admin: TestClient, path: str) -> None:
    assert admin.get(f"{API}/browse", params={"path": path}).status_code == 400


def test_browse_requires_login(app: FastAPI) -> None:
    admin_client(app)  # finish setup
    assert TestClient(app).get(f"{API}/browse").status_code == 401


# --- libraries -------------------------------------------------------------------


def create(admin: TestClient, name: str, path: str, type_: str = "movies") -> dict[str, object]:
    response = admin.post(f"{API}/libraries", json={"name": name, "type": type_, "path": path})
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def test_create_list_update_delete(admin: TestClient, media: Path) -> None:
    created = create(admin, " Movies ", "Movies")
    assert created["name"] == "Movies"
    assert created["path"] == str(media.resolve() / "Movies")
    assert created["relative_path"] == "Movies"

    assert [lib["name"] for lib in admin.get(f"{API}/libraries").json()] == ["Movies"]
    updated = admin.patch(
        f"{API}/libraries/{created['id']}", json={"name": "Films", "type": "other"}
    )
    assert updated.json()["name"] == "Films"
    assert updated.json()["type"] == "other"

    assert admin.delete(f"{API}/libraries/{created['id']}").status_code == 204
    assert admin.get(f"{API}/libraries").json() == []
    assert (media / "Movies" / "film.mkv").exists()  # files never touched


def test_absolute_container_path_accepted(admin: TestClient, media: Path) -> None:
    create(admin, "TV", str(media / "TV"), "tv")


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("", "choose_a_subfolder"),
        ("..", "path_not_allowed"),
        ("/etc", "path_not_allowed"),
        ("Nope", "path_not_allowed"),
        ("Movies/film.mkv", "not_a_folder"),
    ],
)
def test_create_rejects_bad_paths(admin: TestClient, path: str, code: str) -> None:
    response = admin.post(f"{API}/libraries", json={"name": "X", "type": "movies", "path": path})
    assert response.status_code == 400
    assert response.json()["detail"] == code


@pytest.mark.parametrize("second", ["Movies", "Movies/Action"])
def test_libraries_cannot_overlap(admin: TestClient, second: str) -> None:
    create(admin, "Movies", "Movies")
    response = admin.post(f"{API}/libraries", json={"name": "B", "type": "movies", "path": second})
    assert response.status_code == 409
    assert response.json()["detail"] == "path_overlaps_library"


def test_parent_of_existing_library_rejected(admin: TestClient) -> None:
    create(admin, "Action", "Movies/Action")
    response = admin.post(
        f"{API}/libraries", json={"name": "All", "type": "movies", "path": "Movies"}
    )
    assert response.json()["detail"] == "path_overlaps_library"


def test_duplicate_name_rejected(admin: TestClient) -> None:
    create(admin, "Movies", "Movies")
    response = admin.post(f"{API}/libraries", json={"name": "Movies", "type": "tv", "path": "TV"})
    assert response.status_code == 409
    assert response.json()["detail"] == "name_taken"


def test_invalid_type_and_unknown_fields(admin: TestClient) -> None:
    bad_type = {"name": "X", "type": "music", "path": "Other"}
    assert admin.post(f"{API}/libraries", json=bad_type).status_code == 422
    extra = {"name": "X", "type": "other", "path": "Other", "delete_files": True}
    assert admin.post(f"{API}/libraries", json=extra).status_code == 422


def test_mutations_need_csrf(app: FastAPI) -> None:
    admin = admin_client(app)
    del admin.headers["X-CSRF-Token"]
    body = {"name": "X", "type": "other", "path": "Other"}
    assert admin.post(f"{API}/libraries", json=body).status_code == 403


def test_missing_media_root(settings: Settings, tmp_path: Path) -> None:
    settings = settings.model_copy(update={"media_root": tmp_path / "not-mounted"})
    application = create_app(settings, gateways=frozenset())
    with TestClient(application):
        admin = admin_client(application)
        assert admin.get(f"{API}/libraries").json()["detail"] == "media_root_missing"


def test_unreadable_folder_is_reported(admin: TestClient, media: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root can read everything")
    locked = media / "Locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        assert admin.get(f"{API}/browse", params={"path": "Locked"}).status_code == 400
    finally:
        locked.chmod(0o755)
