"""The planner is the heart of ReelHaven: these tests are deliberately exhaustive."""

from typing import Any

import pytest

from reelhaven.media.info import MediaInfo, Stream
from reelhaven.planner import Plan, plan
from reelhaven.policy import LanguagePolicy

DEFAULT = LanguagePolicy()


def video(**kw: Any) -> Stream:
    return Stream(index=0, kind="video", codec="h264", width=1920, height=1080, **kw)


def audio(
    index: int,
    language: str | None,
    *,
    default: bool = False,
    commentary: bool = False,
    bit_rate: int | None = 640_000,
    title: str | None = None,
) -> Stream:
    return Stream(
        index=index,
        kind="audio",
        codec="ac3",
        language=language,
        default=default,
        commentary=commentary,
        bit_rate=bit_rate,
        title=title,
    )


def sub(
    index: int,
    language: str | None,
    *,
    default: bool = False,
    forced: bool = False,
    sdh: bool = False,
    image: bool = False,
    commentary: bool = False,
) -> Stream:
    return Stream(
        index=index,
        kind="subtitle",
        codec="hdmv_pgs_subtitle" if image else "subrip",
        language=language,
        default=default,
        forced=forced,
        hearing_impaired=sdh,
        image_based=image,
        commentary=commentary,
    )


def media(*streams: Stream, hdr: str = "sdr") -> MediaInfo:
    return MediaInfo(
        container="matroska,webm",
        duration_s=1000.0,
        size_bytes=10**9,
        bit_rate=None,
        streams=[video(hdr=hdr), *streams],
    )


def kept(p: Plan, kind: str) -> list[int]:
    return [t.index for t in p.tracks if t.kind == kind and t.keep]


def defaults(p: Plan) -> list[int]:
    return [t.index for t in p.tracks if t.keep and t.default_after]


def apply(info: MediaInfo, p: Plan) -> MediaInfo:
    """What the file looks like after the plan is carried out."""
    by_index = {t.index: t for t in p.tracks}
    streams = []
    for s in info.streams:
        track = by_index.get(s.index)
        if track is None:
            streams.append(s)
        elif track.keep:
            streams.append(s.model_copy(update={"default": track.default_after}))
    return info.model_copy(update={"streams": streams})


# --- the synthetic test-media scenarios ------------------------------------------------


def test_english_only_with_default_english_subtitle() -> None:
    info = media(audio(1, "eng", default=True), sub(2, "eng", default=True))
    p = plan(info, "eng", DEFAULT)
    # English audio for an English viewer: a full English subtitle shouldn't play by default.
    assert p.action == "remux"
    assert kept(p, "audio") == [1] and kept(p, "subtitle") == [2]
    assert defaults(p) == [1]
    assert "Clear default: subtitle English (full)." in p.details


def test_english_only_already_right_is_skipped() -> None:
    p = plan(media(audio(1, "eng", default=True), sub(2, "eng")), "eng", DEFAULT)
    assert p.action == "skip"
    assert p.summary == "Original language: English. Nothing to change."
    assert p.removed_bytes == 0


def test_foreign_original_with_english_subtitles() -> None:
    info = media(audio(1, "jpn", default=True), sub(2, "eng"), sub(3, "jpn"))
    p = plan(info, "jpn", DEFAULT)
    assert kept(p, "audio") == [1]
    assert kept(p, "subtitle") == [2, 3]  # Japanese is wanted: it's the original
    assert defaults(p) == [1, 2]  # Japanese audio + full English subtitles
    assert p.action == "remux"


def test_multi_language_remux_keeps_english_and_forced() -> None:
    info = media(
        audio(1, "eng", default=True),
        audio(2, "eng", commentary=True),
        audio(3, "fra"),
        audio(4, "deu"),
        audio(5, "spa"),
        sub(6, "eng"),
        sub(7, "eng", default=True, forced=True),
        sub(8, "eng", sdh=True),
        sub(9, "fra"),
        sub(10, "deu"),
        sub(11, "spa"),
    )
    p = plan(info, "eng", DEFAULT)
    assert kept(p, "audio") == [1, 2]
    assert kept(p, "subtitle") == [6, 7, 8]
    assert defaults(p) == [1, 7]  # English audio, English forced subtitles
    assert p.removed_bytes == 3 * 640_000 * 1000 // 8
    assert p.summary == (
        "Original language: English. Will remove 3 audio tracks, remove 3 subtitle tracks."
    )
    assert "Remove audio: French, German, Spanish." in p.details


def test_foreign_only_with_unknown_original_is_left_alone() -> None:
    info = media(audio(1, "deu", default=True), sub(2, "deu"))
    p = plan(info, None, DEFAULT)
    assert p.action == "skip"
    assert p.flags == ["no_wanted_audio"]
    assert kept(p, "audio") == [1] and kept(p, "subtitle") == [2]


def test_foreign_only_with_known_original_is_kept() -> None:
    info = media(audio(1, "deu", default=True), sub(2, "deu"))
    p = plan(info, "deu", DEFAULT)
    assert p.action == "skip"
    assert p.flags == []


def test_untagged_audio_is_kept_and_never_wrong_language() -> None:
    info = media(audio(1, None, default=True), audio(2, None), sub(3, None))
    p = plan(info, "eng", DEFAULT)
    assert p.action == "skip"
    assert "wrong_language" not in p.flags
    assert kept(p, "audio") == [1, 2] and kept(p, "subtitle") == [3]


def test_untagged_can_be_treated_as_a_language() -> None:
    policy = LanguagePolicy(untagged="eng")
    p = plan(media(audio(1, None, default=True), audio(2, "fra")), "eng", policy)
    assert kept(p, "audio") == [1]


# --- wrong language and safety ------------------------------------------------------------


def test_wrong_language_file_is_flagged_not_changed() -> None:
    info = media(audio(1, "spa", default=True), sub(2, "spa"), sub(3, "eng"))
    p = plan(info, "eng", DEFAULT)
    assert p.flags == ["wrong_language"]
    assert p.action == "skip"
    assert all(t.keep for t in p.tracks)
    assert any("flagged for review" in d for d in p.details)


def test_never_removes_the_last_main_audio_track() -> None:
    # Only a commentary in a wanted language: the Spanish main track must stay.
    info = media(audio(1, "spa", default=True), audio(2, "eng", commentary=True))
    p = plan(info, "eng", DEFAULT)
    assert kept(p, "audio") == [1, 2]
    assert p.action == "skip"


def test_untagged_plus_unwanted_does_not_flag_wrong_language() -> None:
    info = media(audio(1, "spa", default=True), audio(2, None))
    p = plan(info, "eng", DEFAULT)
    assert "wrong_language" not in p.flags
    assert kept(p, "audio") == [1, 2] or kept(p, "audio") == [2]


def test_original_unknown_keeps_viewer_language_only() -> None:
    info = media(audio(1, "fra", default=True), audio(2, "eng"))
    p = plan(info, None, DEFAULT)
    assert kept(p, "audio") == [2]
    assert defaults(p) == [2]


def test_no_audio_at_all() -> None:
    p = plan(media(sub(1, "eng")), "eng", DEFAULT)
    assert "no_audio" in p.flags
    assert p.action == "skip"


# --- toggles -------------------------------------------------------------------------------


def test_commentary_toggle() -> None:
    info = media(
        audio(1, "eng", default=True),
        audio(2, "eng", commentary=True),
        sub(3, "eng", commentary=True),
    )
    p = plan(info, "eng", LanguagePolicy(keep_commentary=False))
    assert kept(p, "audio") == [1]
    assert kept(p, "subtitle") == []


@pytest.mark.parametrize(
    ("toggle", "expected"),
    [
        ({"keep_subtitles_full": False}, [3, 4]),
        ({"keep_subtitles_forced": False}, [2, 4]),
        ({"keep_subtitles_sdh": False}, [2, 3]),
    ],
)
def test_subtitle_type_toggles(toggle: dict[str, bool], expected: list[int]) -> None:
    info = media(
        audio(1, "eng", default=True),
        sub(2, "eng"),
        sub(3, "eng", forced=True),
        sub(4, "eng", sdh=True),
    )
    assert kept(plan(info, "eng", LanguagePolicy.model_validate(toggle)), "subtitle") == expected


def test_set_defaults_off_only_removes() -> None:
    info = media(
        audio(1, "fra"), audio(2, "eng", default=True), audio(3, "deu"), sub(4, "eng", default=True)
    )
    p = plan(info, "fra", LanguagePolicy(set_defaults=False))
    assert kept(p, "audio") == [1, 2]
    assert defaults(p) == [2, 4]


def test_original_off_keeps_only_listed_languages() -> None:
    info = media(audio(1, "fra", default=True), audio(2, "eng"))
    p = plan(info, "fra", LanguagePolicy(keep_original=False))
    assert kept(p, "audio") == [2]
    assert defaults(p) == [2]


def test_non_english_viewer() -> None:
    info = media(
        audio(1, "eng", default=True),
        audio(2, "deu"),
        sub(3, "eng"),
        sub(4, "deu"),
        sub(5, "deu", forced=True),
        sub(6, "fra"),
    )
    policy = LanguagePolicy(keep_languages=["German"])
    p = plan(info, "eng", policy)
    assert kept(p, "audio") == [1, 2]
    assert kept(p, "subtitle") == [3, 4, 5]
    assert defaults(p) == [1, 4]  # original English audio, full German subtitles


# --- defaults (§8.3) --------------------------------------------------------------------------


def test_default_audio_prefers_original_then_viewer() -> None:
    info = media(
        audio(1, "eng", default=True), audio(2, "jpn"), sub(3, "eng"), sub(4, "eng", sdh=True)
    )
    p = plan(info, "jpn", DEFAULT)
    assert defaults(p) == [2, 3]  # Japanese audio, full English (not SDH)


def test_sdh_is_fallback_for_foreign_audio() -> None:
    info = media(audio(1, "kor", default=True), sub(2, "eng", sdh=True))
    assert defaults(plan(info, "kor", DEFAULT)) == [1, 2]


def test_existing_default_preferred_among_equal_tracks() -> None:
    info = media(audio(1, "eng"), audio(2, "eng", default=True))
    assert defaults(plan(info, "eng", DEFAULT)) == [2]


def test_untagged_default_audio_leaves_subtitle_defaults() -> None:
    info = media(
        audio(1, None, default=True), sub(2, "eng", default=True), sub(3, "eng", forced=True)
    )
    p = plan(info, None, DEFAULT)
    assert defaults(p) == [1, 2]


# --- other ---------------------------------------------------------------------------------------


def test_image_subtitles_follow_language_rules() -> None:
    info = media(
        audio(1, "eng", default=True), sub(2, "eng", image=True), sub(3, "fra", image=True)
    )
    assert kept(plan(info, "eng", DEFAULT), "subtitle") == [2]


def test_dolby_vision_is_flagged_but_can_be_remuxed() -> None:
    p = plan(
        media(audio(1, "eng", default=True), audio(2, "fra"), hdr="dolby_vision"), "eng", DEFAULT
    )
    assert "dolby_vision" in p.flags
    assert p.action == "remux"


def test_removed_bytes_unknown_without_bit_rates() -> None:
    p = plan(media(audio(1, "eng", default=True), audio(2, "fra", bit_rate=None)), "eng", DEFAULT)
    assert p.removed_bytes is None


SCENARIOS: list[tuple[MediaInfo, str | None, LanguagePolicy]] = [
    (media(audio(1, "eng", default=True), sub(2, "eng", default=True)), "eng", DEFAULT),
    (media(audio(1, "jpn", default=True), sub(2, "eng"), sub(3, "jpn")), "jpn", DEFAULT),
    (
        media(
            audio(1, "eng", default=True),
            audio(2, "eng", commentary=True),
            audio(3, "fra"),
            sub(4, "eng"),
            sub(5, "eng", forced=True),
            sub(6, "fra"),
        ),
        "eng",
        DEFAULT,
    ),
    (
        media(audio(1, "fra"), audio(2, "eng", default=True), sub(3, "eng", default=True)),
        "fra",
        DEFAULT,
    ),
    (
        media(audio(1, "eng", default=True), audio(2, "deu"), sub(3, "deu", forced=True)),
        "eng",
        LanguagePolicy(keep_languages=["deu"]),
    ),
    (media(audio(1, None), audio(2, "fra", default=True)), None, LanguagePolicy(untagged="eng")),
]


@pytest.mark.parametrize(("info", "original", "policy"), SCENARIOS)
def test_planning_is_idempotent(
    info: MediaInfo, original: str | None, policy: LanguagePolicy
) -> None:
    """After a remux, planning the result again must find nothing to do."""
    first = plan(info, original, policy)
    second = plan(apply(info, first), original, policy)
    assert second.action == "skip", second.details


def test_video_and_attachments_never_appear_in_plan() -> None:
    info = media(audio(1, "eng", default=True))
    info.streams.append(Stream(index=2, kind="attachment", codec="ttf"))
    assert {t.kind for t in plan(info, "eng", DEFAULT).tracks} == {"audio"}


# --- policy validation ------------------------------------------------------------------------


def test_policy_normalises_languages() -> None:
    policy = LanguagePolicy(keep_languages=["English", "fr", "eng"], untagged="German")
    assert policy.keep_languages == ["eng", "fra"]
    assert policy.untagged == "deu"
    assert policy.viewer_language == "eng"


@pytest.mark.parametrize(
    "bad",
    [{"keep_languages": []}, {"keep_languages": ["und"]}, {"untagged": "und"}, {"extra": True}],
)
def test_policy_rejects_bad_values(bad: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        LanguagePolicy.model_validate(bad)


def test_mp4_always_has_a_default_subtitle() -> None:
    """MP4 enables the first subtitle when none is default; the plan must agree."""
    info = media(audio(1, "eng", default=True), sub(2, "eng", default=True), sub(3, "fra"))
    info = info.model_copy(update={"container": "mov,mp4,m4a,3gp,3g2,mj2"})
    p = plan(info, "eng", DEFAULT)
    assert defaults(p) == [1, 2]
    assert not any("Clear default" in d for d in p.details)
    assert plan(apply(info, p), "eng", DEFAULT).action == "skip"
