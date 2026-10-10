"""Jobs → Upcoming: the backlog not yet queued, in the order it will run."""

import os
from dataclasses import replace

import pytest
from fastapi import FastAPI

from reelhaven.automation import FileState, Upcoming, upcoming
from reelhaven.config import Settings
from reelhaven.planner import Plan
from tests.helpers import API
from tests.media_fixtures import FFMPEG
from tests.test_automation import fp
from tests.test_encode_pipeline import FAST, app, setup  # noqa: F401 - shared fixture


def _actions(items: list[Upcoming]) -> list[tuple[int, str, str]]:
    return [(u.file_id, u.action, u.why) for u in items]


def test_upcoming_follows_the_queue_rules() -> None:
    wrong = fp(7, "remux")
    assert wrong.plan is not None
    wrong = replace(
        wrong,
        plan=Plan(**{**wrong.plan.model_dump(), "action": "skip", "flags": ["wrong_language"]}),
    )
    plans = [
        fp(1, "remux"),
        fp(2, "encode"),
        fp(3, "skip"),  # nothing to do
        fp(4, "remux"),  # already queued
        fp(5, "remux"),  # failed, unchanged since
        replace(fp(6, "remux"), language_pending=True),  # waits for its language
        wrong,
    ]
    state = FileState(1, 1)

    def run(automatic: bool, allowed: bool, action: str = "flag") -> list[Upcoming]:
        return upcoming(
            plans,
            automatic=automatic,
            active={4},
            gave_up={5: state},
            current={5: state},
            encodes_allowed=allowed,
            wrong_language_action=action,
        )

    assert _actions(run(True, True)) == [
        (1, "remux", "next"),
        (2, "encode", "next"),
    ]
    # Re-encodes wait for a test run; libraries that aren't automatic wait for you.
    assert _actions(run(True, False))[1] == (
        2,
        "encode",
        "test_run",
    )
    assert {u.why for u in run(False, True)} == {"not_automatic"}
    # Wrong-language files are upcoming when the library quarantines them.
    quarantine = run(True, True, "quarantine")
    assert _actions(quarantine)[-1] == (7, "quarantine", "next") and quarantine[-1].saved is None


@pytest.mark.skipif(FFMPEG is None and not os.environ.get("CI"), reason="ffmpeg not installed")
def test_upcoming_api(app: FastAPI, settings: Settings) -> None:  # noqa: F811
    admin, _lib, _path = setup(app, settings, FAST)
    page = admin.get(f"{API}/upcoming").json()
    (item,) = page["items"]
    assert (item["action"], item["why"], item["library_name"]) == (
        "encode",
        "not_automatic",
        "Movies",
    )
    assert page["counts"] == {"next": 0, "test_run": 0, "not_automatic": 1}
    assert page["total"] == 1 and page["saved"] == (item["saved"] or 0)
    assert admin.get(f"{API}/upcoming", params={"why": "next"}).json()["items"] == []
