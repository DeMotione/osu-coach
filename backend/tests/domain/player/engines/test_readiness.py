"""Readiness as every engine gives it: the clean-pass chance and the star ratings to compare with."""

import pytest

from osu_coach.domain.player.engines.readiness import (
    MAX_GAP,
    PASS_AT_LEVEL,
    SkillAt,
    default_target,
    pass_chance,
    readiness,
    targets,
)


def test_the_pass_chance_is_the_comfort_levels_there_and_falls_with_every_star():
    chances = [pass_chance(6.0, t) for t in (4.0, 5.0, 6.0, 6.5, 7.0, 8.0)]
    assert chances == sorted(chances, reverse=True)
    assert chances[2] == PASS_AT_LEVEL
    assert 0.3 < chances[4] < 0.4 and chances[5] < 0.15 and chances[0] > 0.95


def test_the_weakest_is_the_lowest_known_score():
    skills = {"aim": SkillAt(60.0, -5.0, 1.2), "speed": SkillAt(30.0, -9.0, 1.3), "reading": None}
    assert readiness(6.0, 7.0, skills).weakest == "speed"
    assert readiness(6.0, 7.0, {"aim": None}).weakest is None


@pytest.mark.parametrize("comfort", [1.0, 1.4, 4.9, 6.3, 7.0, 11.4, 12.6, 12.9, 13.0])
def test_the_star_ratings_to_compare_with(comfort):
    options = targets(comfort)
    stars = [s for s, _ in options]
    base = round(comfort, 1)
    assert stars == sorted(stars) and len(set(stars)) == len(stars)
    assert stars[0] == 1.0 and stars[-1] == 13.0
    assert (base, False) in options and (default_target(comfort), False) in options
    assert {float(s) for s in range(1, 14)} <= set(stars)  # every whole star
    for s, locked in options:  # only more than 2★ above is locked: any easier star rating is open
        assert locked == (s > base + MAX_GAP + 1e-9), s
    assert all(s == int(s) for s, locked in options if locked)


@pytest.mark.parametrize(
    "comfort,near,default",
    [(6.15, [5.5, 6.0, 6.5, 7.0], 6.2), (6.55, [6.0, 6.5, 7.0, 7.5], round(6.55, 1)), (6.0, [5.5, 6.0, 6.5, 7.0], 6.0)],
)
def test_half_stars_near_the_comfort_level(comfort, near, default):
    """The two half stars either side of the comfort level, the whole stars and the comfort level itself."""
    stars = [s for s, _ in targets(comfort)]
    base = round(comfort, 1)
    assert {s for s in stars if s != int(s)} - {base} == {s for s in near if s != int(s)} - {base}
    assert set(near) <= set(stars) and default_target(comfort) == default
