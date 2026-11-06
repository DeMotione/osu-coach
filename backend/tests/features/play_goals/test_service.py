"""Play goals: reading the beatmap a goal names."""

import pytest

from osu_coach.features.play_goals.service import beatmap_id


@pytest.mark.parametrize(
    "value, expected",
    [
        ("https://osu.ppy.sh/b/1234", 1234),
        ("https://osu.ppy.sh/beatmaps/1234", 1234),
        ("https://osu.ppy.sh/beatmapsets/5#osu/1234", 1234),
    ],
)
def test_target_ids(value, expected):
    assert beatmap_id(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.test/b/1234",
        "https://osu.ppy.sh/beatmapsets/5",
        "https://osu.ppy.sh/beatmapsets/5#mania/1234",
        "file:///etc/passwd",
        "1234",
        "0",
    ],
)
def test_rejects_non_difficulty_and_arbitrary_urls(value):
    with pytest.raises(ValueError):
        beatmap_id(value)
