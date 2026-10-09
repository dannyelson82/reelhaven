"""Half-step profile quality (ADR-0031): room to dial in between the whole levels."""

import pytest
from pydantic import ValidationError

from reelhaven.encode_planner import expected_bitrate, profile_fingerprint
from reelhaven.profiles import ProfileSettings
from reelhaven.quality import quality_value


def test_half_steps_lie_between_their_neighbours() -> None:
    assert quality_value("cpu", "hevc", 6) == 24
    assert quality_value("cpu", "hevc", 6.5) == 23  # between 24 and 22
    assert quality_value("cpu", "hevc", 5.5) == 24.5  # x265 takes fractions
    assert quality_value("nvenc", "hevc", 1.5) == 35.5  # so does NVENC
    # Quick Sync takes whole numbers: a half step rounds towards the better quality.
    assert quality_value("qsv", "hevc", 7.5) == 17  # between 18 and 17
    assert quality_value("cpu", "av1", 1.5) == 44  # SVT-AV1 too: between 46 and 43
    for bad in (0.5, 10.5, 6.3):
        with pytest.raises(ValueError):
            quality_value("cpu", "hevc", bad)


def test_profiles_take_half_steps_and_keep_whole_levels_whole() -> None:
    assert ProfileSettings(quality=6.5).model_dump()["quality"] == 6.5
    whole = ProfileSettings.model_validate({"quality": 6.0})
    assert whole.model_dump()["quality"] == 6 and isinstance(whole.model_dump()["quality"], int)
    # Existing profiles keep their fingerprint, so approved test runs stay approved.
    assert profile_fingerprint(whole) == profile_fingerprint(ProfileSettings(quality=6))
    assert profile_fingerprint(ProfileSettings(quality=6.5)) != profile_fingerprint(whole)
    with pytest.raises(ValidationError):
        ProfileSettings(quality=6.3)


def test_expected_bitrate_of_a_half_step() -> None:
    six, seven = (expected_bitrate("hevc", q, 1920, 1080, 24) for q in (6, 7))
    assert six < expected_bitrate("hevc", 6.5, 1920, 1080, 24) < seven
    assert expected_bitrate("hevc", 10, 1920, 1080, 24) > seven  # the top level still works
