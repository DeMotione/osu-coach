"""Star Levels: a skill's playlist is made around the skill's own star level, not the comfort level moved by κ."""

from types import SimpleNamespace

import pytest

from osu_coach.domain.player.engines.irt.engine import adapter
from osu_coach.domain.player.messages import Message
from osu_coach.domain.player.records import SkillRating
from osu_coach.features.maps.service import _options, skill_levels

LEVEL = 6.4


def rating(measured: float | None, state: str = "measured") -> SkillRating:
    score = adapter(measured, LEVEL) if measured is not None else None
    return SkillRating(score=score, maps=10, reason=Message("irt_measured"), measured=measured, state=state)


def profile(engine: str = "irt"):
    skills = {
        "aim": rating(7.1),
        "speed": rating(6.8, "provisional"),
        "reading": rating(8.0, "untested"),  # a lower bound: no level
        "consistency": SkillRating(score=34.0, maps=20, reason=Message("irt_measured")),
    }
    return SimpleNamespace(
        engine=engine,
        skill_ratings=skills,
        weaknesses=[],
        levels=SimpleNamespace(comfort_stars=LEVEL, level_stars=LEVEL),
    )


def test_star_levels_are_the_measured_skills_own():
    assert skill_levels(profile()) == {"aim": 7.1, "speed": 6.8}
    assert skill_levels(profile("comfort")) == {} and skill_levels(None) == {}


def test_a_playlist_is_made_around_the_skills_own_level():
    target, _, abilities, theta, source, kappa = _options(profile(), "aim", "aim,consistency", None, None, 0.8, 0.3)
    assert (target, theta, kappa) == ("aim", 7.1, 0.0)
    assert abilities["aim"] == 50 and abilities["consistency"] == 34.0  # typical at its own level
    assert source == "Your Jumps level"


def test_without_a_level_the_comfort_level_and_kappa_stay():
    _, _, abilities, theta, _, kappa = _options(profile(), "consistency", None, None, None, 0.8, 0.3)
    assert (theta, kappa) == (LEVEL, 0.8)
    assert abilities["aim"] == pytest.approx(adapter(7.1, LEVEL))
    _, _, _, theta, source, kappa = _options(profile(), "aim", None, None, 5.0, 0.8, 0.3)  # comfort given by hand
    assert (theta, source, kappa) == (5.0, "Manual", 0.8)
    _, _, _, theta, _, kappa = _options(profile("comfort"), "aim", None, None, None, 0.8, 0.3)
    assert (theta, kappa) == (LEVEL, 0.8)
    _, _, _, theta, _, _ = _options(profile(), "aim", None, None, None, 0.8, 0.3, around_skill=False)
    assert theta == LEVEL


def test_manual_ratings_still_win_around_the_level():
    _, _, abilities, theta, _, _ = _options(profile(), "speed", None, '{"speed": 60}', None, 0.5, 0.3)
    assert theta == 6.8 and abilities["speed"] == 60
