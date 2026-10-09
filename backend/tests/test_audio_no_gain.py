"""Converting the audio didn't make the file smaller (owner report).

A FLAC track of a plain tone is tiny, so converting it to E-AC-3 makes the file
bigger. The job must still carry out the language changes, remember not to try
that conversion again, and keep the original when nothing else was planned.
"""

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from reelhaven.config import Settings
from reelhaven.db import Database, MediaFile
from reelhaven.media.probe import probe
from reelhaven.planner import (
    TrackPlan,
    conversion_signature,
    has_track_changes,
    plan,
    without_conversions,
)
from reelhaven.policy import LanguagePolicy
from tests.helpers import API, admin_client
from tests.media_fixtures import Audio, Spec, make
from tests.test_planner import audio, media
from tests.test_remux import OLD, app, jobs  # noqa: F401 - shared fixture

PROFILE = {
    "codec": "hevc",
    "quality": 5,
    "speed": "fast",
    "audio": "compress_lossless",
    "audio_codec": "eac3",
}


def track(index: int, **convert: Any) -> TrackPlan:
    return TrackPlan(
        index=index, kind="audio", language="eng", title=None, keep=True,
        default_before=True, default_after=True, reason="", **convert,
    )  # fmt: skip


def test_conversion_signature() -> None:
    assert conversion_signature([track(1)]) is None
    eac3 = conversion_signature([track(1, convert_codec="eac3", convert_kbps=640)])
    assert eac3 is not None
    assert eac3 == conversion_signature([track(1, convert_codec="eac3", convert_kbps=640)])
    assert eac3 != conversion_signature([track(1, convert_codec="eac3", convert_kbps=448)])


def test_without_conversions_keeps_the_track_changes() -> None:
    info = media(audio(1, "eng", default=True), audio(2, "fra"))
    p = plan(info, "eng", LanguagePolicy())
    p.tracks[0].convert_codec, p.tracks[0].convert_kbps = "eac3", 640
    stripped = without_conversions(p)
    assert stripped.action == "remux" and has_track_changes(stripped)
    assert all(t.convert_codec is None for t in stripped.tracks)
    assert p.tracks[0].convert_codec == "eac3"  # the original plan is untouched

    only_audio = plan(media(audio(1, "eng", default=True)), "eng", LanguagePolicy())
    only_audio.tracks[0].convert_codec = "eac3"
    assert without_conversions(only_audio).action == "skip"


def setup(app: FastAPI, settings: Settings, spec: Spec) -> tuple[TestClient, int, Path]:  # noqa: F811
    root = settings.media_root / "Movies"
    path = root / "Film (2020)" / "film.mkv"
    path.parent.mkdir(parents=True)
    os.utime(make(path, spec), (OLD, OLD))
    admin = admin_client(app)
    lib = admin.post(
        f"{API}/libraries", json={"name": "Movies", "type": "movies", "path": "Movies"}
    ).json()["id"]
    profile = admin.post(f"{API}/profiles", json={"name": "T", "settings": PROFILE}).json()
    admin.put(f"{API}/libraries/{lib}/profile", json={"profile_id": profile["id"]})
    admin.post(f"{API}/libraries/{lib}/scan")
    app.state.scanner.wait(lib, timeout=60)
    for title in admin.get(f"{API}/libraries/{lib}/titles").json()["items"]:
        admin.put(f"{API}/titles/{title['id']}/language", json={"language": "eng"})
    return admin, lib, path


def apply(app: FastAPI, admin: TestClient, lib: int) -> None:  # noqa: F811
    dry = admin.get(f"{API}/libraries/{lib}/dry-run").json()
    count = dry["remux"]
    assert count == 1, dry
    assert (
        admin.post(
            f"{API}/libraries/{lib}/apply",
            json={"expected_count": count, "only_track_changes": True},
        ).json()["queued"]
        == 1
    )
    assert app.state.queue.wait_idle(120)


def no_gain_audio(app: FastAPI) -> str | None:  # noqa: F811
    db: Database = app.state.db
    with db.read() as session:
        return session.scalars(select(MediaFile)).one().no_gain_audio


def test_language_changes_still_happen(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    spec = Spec(
        codec="libx265",
        audio=[Audio("eng", default=True, codec="flac"), Audio("fre", codec="aac")],
    )
    admin, lib, path = setup(app, settings, spec)
    apply(app, admin, lib)
    job = jobs(admin)[0]
    assert (job["status"], job["outcome"]) == ("done", "replaced"), job["error"]
    after = probe(path).of_kind("audio")
    assert [(a.language, a.codec) for a in after] == [("eng", "flac")]  # French gone, FLAC kept
    assert no_gain_audio(app) is not None
    # Nothing left to do: the conversion isn't planned again.
    admin.post(f"{API}/libraries/{lib}/scan")
    app.state.scanner.wait(lib, timeout=60)
    assert admin.get(f"{API}/libraries/{lib}/dry-run").json()["remux"] == 0


def test_conversion_alone_keeps_the_original(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    spec = Spec(codec="libx265", audio=[Audio("eng", default=True, codec="flac")])
    admin, lib, path = setup(app, settings, spec)
    before = path.read_bytes()
    apply(app, admin, lib)
    job = jobs(admin)[0]
    assert (job["status"], job["outcome"]) == ("done", "no_gain"), job["error"]
    assert path.read_bytes() == before
    assert no_gain_audio(app) is not None
    assert admin.get(f"{API}/libraries/{lib}/dry-run").json()["remux"] == 0
