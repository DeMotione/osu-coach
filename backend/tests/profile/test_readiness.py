"""Readiness for another star rating: the comfort-level scores moved to it and the clean-pass chance."""

import math

import pytest

from osu_coach.profile.domain.demand import log_demand
from osu_coach.profile.domain.experimental import POINTS, _accuracy_expected, _expected
from osu_coach.profile.domain.readiness import (
    MAX_GAP,
    PASS_AT_LEVEL,
    SKILLS,
    _sigma_for,
    compare_at,
    default_target,
    scores_at,
    targets,
)

WINDOWS = [(79.5 - 6 * 8, 1.0), (79.5 - 6 * 9, 1.0)]  # OD 8 and OD 9


def rows(theta, scores=None):
    """Comfort-level rating rows at ``theta`` with these scores (50 = typical everywhere by default)."""
    scores = scores or {}
    out = {k: {"score": scores.get(k, 50.0), "maps": 20, "measured": 1.0, "expected": 1.0} for k in SKILLS}
    out["accuracy"].update(measured=_accuracy_expected(WINDOWS, theta), od_windows=WINDOWS)
    out["stamina"]["parts"] = [{"duration": 30, "maps": 10, "measured": _expected("stamina", theta, duration=30)}]
    out["consistency"] = {"score": 70.0}
    return out


def test_at_the_comfort_level_the_scores_are_the_comfort_scores():
    r = rows(6.0, {"aim": 82.0, "speed": 31.5})
    at = scores_at(r, 6.0, 6.0)
    assert set(at) == set(SKILLS)  # consistency has its own card
    for skill in SKILLS:
        assert at[skill]["score"] == pytest.approx(r[skill]["score"], abs=0.05), skill
        assert at[skill]["change"] == pytest.approx(0, abs=0.05) and at[skill]["demand"] == pytest.approx(1)


@pytest.mark.parametrize("theta", [2.5, 4.9, 6.3, 7.3, 10.5])
def test_every_score_falls_as_the_star_rating_rises(theta):
    r = rows(theta, {"aim": 70.0, "speed": 40.0, "accuracy": 60.0})
    for skill in SKILLS:
        series = [scores_at(r, theta, theta + d)[skill]["score"] for d in (-2, -1, -0.5, 0, 0.5, 1, 1.5, 2)]
        assert series == sorted(series, reverse=True), skill
        assert series[-1] < series[3] < series[0] or series[0] == 100, skill


def test_a_score_falls_by_the_skill_points_per_doubling_of_its_demand():
    at = scores_at(rows(5.0, {"aim": 60.0, "speed": 60.0}), 5.0, 6.0)
    for skill in ("aim", "speed"):
        extra = log_demand(skill, 6.0) - log_demand(skill, 5.0)
        assert at[skill]["demand"] == pytest.approx(2**extra, abs=1e-3)
        assert at[skill]["change"] == pytest.approx(-POINTS[skill] * extra, abs=0.06)
    assert at["speed"]["change"] < at["aim"]["change"] < -3  # a star costs tapping more points than aim here


def test_scores_stay_between_0_and_100():
    r = rows(5.0, {"aim": 100.0, "speed": 2.0})
    harder, easier = scores_at(r, 5.0, 7.0), scores_at(r, 5.0, 3.0)
    assert harder["aim"]["score"] < 100 and harder["speed"]["score"] == 0
    assert easier["aim"]["score"] == 100 and easier["aim"]["change"] == 0


def test_narrower_hit_windows_cost_accuracy():
    at = scores_at(rows(6.0, {"accuracy": 70.0}), 6.0, 7.0)["accuracy"]
    assert at["demand"] > 1 and at["change"] < -2


def test_the_hit_error_spread_is_found_back_from_the_non_300_share():
    for sigma in (8.0, 15.0, 30.0):
        share = sum(w * math.erfc(win / (math.sqrt(2) * sigma)) for win, w in WINDOWS) / 2
        assert _sigma_for(share, WINDOWS) == pytest.approx(sigma, rel=1e-4)


def test_the_pass_chance_is_the_comfort_levels_there_and_falls_with_every_star():
    r = rows(6.0, {"speed": 35.0})
    chances = [compare_at(r, 6.0, t)["pass_chance"] for t in (4.0, 5.0, 6.0, 6.5, 7.0, 8.0)]
    assert chances == sorted(chances, reverse=True)
    assert chances[2] == PASS_AT_LEVEL
    assert 0.3 < chances[4] < 0.4 and chances[5] < 0.15 and chances[0] > 0.95
    assert compare_at(r, 6.0, 7.0)["weakest"] == "speed"


def test_skills_without_a_comfort_score_have_none():
    r = rows(5.0)
    r["aim"]["score"] = None
    r["accuracy"]["od_windows"] = []
    at = scores_at(r, 5.0, 6.0)
    assert at["aim"] is None and at["accuracy"] is None and at["speed"] is not None
    assert all(v is None for v in scores_at(r, None, 6.0).values())


@pytest.mark.parametrize("comfort", [1.0, 1.4, 4.9, 6.3, 7.0, 11.4, 12.6, 12.9, 13.0])
def test_the_star_ratings_to_compare_with(comfort):
    options = targets(comfort)
    stars = [s for s, _ in options]
    base = round(comfort, 1)
    assert stars == sorted(stars) and len(set(stars)) == len(stars)
    assert stars[0] == 1.0 and stars[-1] == 13.0
    assert (base, False) in options and (default_target(comfort), False) in options
    for s, locked in options:  # more than 2★ away is locked, the rest is open
        assert locked == (abs(s - base) > MAX_GAP + 1e-9), s
    open_ = [s for s, locked in options if not locked]
    assert min(b - a for a, b in zip(open_, open_[1:], strict=False)) >= 0.1 - 1e-9 if len(open_) > 1 else True
    assert all(s == int(s) for s, locked in options if locked)
