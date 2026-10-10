"""The review page (ADR-0032)."""

import os
from dataclasses import replace

import pytest
from fastapi import FastAPI

from reelhaven.config import Settings
from reelhaven.db import Job, MediaFile
from reelhaven.review import FileFacts, file_state, review_items
from tests.helpers import API
from tests.media_fixtures import FFMPEG
from tests.test_encode_pipeline import FAST, app, file_id, setup  # noqa: F401

BASE = FileFacts(
    file_id=1,
    library_id=2,
    library_name="Movies",
    relative_path="Film (2020)/film.mkv",
    size=100,
    mtime_ns=5,
)


def _kinds(facts: FileFacts) -> list[str]:
    return [item.kind for item in review_items([facts])]


def test_each_kind() -> None:
    assert _kinds(BASE) == []  # nothing to decide
    assert _kinds(replace(BASE, unreadable="moov atom not found")) == ["unreadable"]
    wrong = review_items(
        [
            replace(
                BASE,
                flags=("wrong_language",),
                original_language="eng",
                audio_languages=("spa", "spa", "fre"),
            )
        ]
    )
    assert [i.kind for i in wrong] == ["wrong_language"]
    assert wrong[0].audio_languages == ("fre", "spa") and wrong[0].original_language == "eng"
    assert _kinds(replace(BASE, flags=("no_wanted_audio",))) == ["wrong_language"]
    assert _kinds(replace(BASE, flags=("dolby_vision",))) == ["skipped"]
    failed = review_items([replace(BASE, failed_job=(9, "decode test failed\nmore"))])
    assert (failed[0].kind, failed[0].detail, failed[0].job_id) == (
        "failed",
        "decode test failed",
        9,
    )
    assert _kinds(replace(BASE, no_gain_video=True)) == ["no_gain"]
    assert _kinds(replace(BASE, language_pending=True)) == ["waiting"]


def test_ignored_until_the_file_changes() -> None:
    facts = replace(BASE, no_gain_audio=True, ignored={"no_gain": file_state(100, 5)})
    assert review_items([facts])[0].ignored is True
    changed = replace(facts, size=90)
    assert review_items([changed])[0].ignored is False


@pytest.mark.skipif(FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed")
def test_review_api(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, lib, _path = setup(app, settings, FAST)
    fid = file_id(admin, lib)
    page = admin.get(f"{API}/review").json()
    assert page["total"] == 0 and page["counts"]["failed"] == 0

    with app.state.db.write() as session:
        media_file = session.get(MediaFile, fid)
        assert media_file is not None
        media_file.no_gain_profile = "abcd1234"
        session.add(
            Job(
                library_id=lib,
                media_file_id=fid,
                type="encode",
                status="failed",
                error="decode test failed at 12s",
                source_path=media_file.path,
                source_size=media_file.size,
                source_mtime_ns=media_file.mtime_ns,
                plan={},
                probe={},
                requested_by="admin",
            )
        )
    from reelhaven.api.review_routes import clear_cache

    clear_cache()
    page = admin.get(f"{API}/review").json()
    assert [i["kind"] for i in page["items"]] == ["failed", "no_gain"]
    assert page["items"][0]["detail"] == "decode test failed at 12s"
    assert page["items"][0]["library_name"] == "Movies"
    assert admin.get(f"{API}/review", params={"kind": "no_gain"}).json()["total"] == 1

    ignored = admin.put(f"{API}/review/ignore", json={"file_id": fid, "kind": "no_gain"})
    assert ignored.status_code == 204
    page = admin.get(f"{API}/review").json()
    assert page["counts"]["no_gain"] == 0 and page["ignored"] == 1
    assert [i["kind"] for i in page["items"]] == ["failed"]
    shown = admin.get(f"{API}/review", params={"show_ignored": True}).json()
    assert [(i["kind"], i["ignored"]) for i in shown["items"]] == [
        ("failed", False),
        ("no_gain", True),
    ]
    admin.put(f"{API}/review/ignore", json={"file_id": fid, "kind": "no_gain", "ignored": False})
    assert admin.get(f"{API}/review").json()["counts"]["no_gain"] == 1
    assert (
        admin.put(f"{API}/review/ignore", json={"file_id": 999, "kind": "failed"}).status_code
        == 404
    )
