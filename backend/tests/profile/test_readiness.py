"""Readiness for another star rating: skill levels in stars, gaps, effective level and clean-pass chance."""

import math

import pytest

from osu_coach.profile.domain.experimental import _accuracy_expected, _expected
from osu_coach.profile.domain.readiness import (
    PASS_AT_LEVEL,
    POINTS_PER_STAR,
    SKILLS,
    _sigma_for,
    compare_at,
    default_target,
    skill_levels,
    targets,
)

WINDOWS = [(79.5 - 6 * 8, 1.0), (79.5 - 6 * 9, 1.0)]  # OD 8 and OD 9


def rows(theta, times=None, success=0.8, tested=1.6, maps=20):
    """Comfort-level rating rows of a player whose skills are ``times`` x what is typical at ``theta``."""
    times = times or {}
    out = {}
    for k in ("aim", "flow_aim", "speed", "sliders", "reading"):
        e = _expected(k, theta)
        out[k] = {
            "maps": maps,
            "measured": e * times.get(k, 1.0),
            "expected": e,
            "tested_demand": e * tested,
            "success_share": success,
            "score": 50.0,
        }
    out["stamina"] = {
        "parts": [
            {
                "duration": d,
                "maps": 10,
                "measured": _expected("stamina", theta, duration=d) * times.get("stamina", 1.0),
                "tested_demand": _expected("stamina", theta, duration=d) * tested,
                "success_share": success,
            }
            for d in (10, 30, 60)
        ]
    }
    # accuracy: a non-300 share x what is typical (higher = worse)
    out["accuracy"] = {
        "score": 50.0,
        "measured": _accuracy_expected(WINDOWS, theta) * times.get("accuracy", 1.0),
        "od_windows": WINDOWS,
    }
    out["consistency"] = {"score": 70.0, "measured": 1.5, "expected": 2.0, "maps": 30}
    return out


@pytest.mark.parametrize("theta", [3.0, 4.9, 7.3])
def test_a_typical_player_is_at_the_comfort_level_in_every_skill(theta):
    levels = skill_levels(rows(theta), theta)
    assert set(levels) == set(SKILLS)  # consistency is no level skill
    for skill, lv in levels.items():
        assert lv["level"] == pytest.approx(theta, abs=0.01), skill
        assert lv["bound"] is None


def test_every_skill_is_equally_short_of_a_harder_map_for_a_typical_player():
    levels = skill_levels(rows(4.9), 4.9)
    at_comfort, harder, ten = compare_at(levels, 4.9), compare_at(levels, 5.9), compare_at(levels, 10.0)
    for skill in SKILLS:
        assert at_comfort["skills"][skill]["score"] == pytest.approx(50)
        assert harder["skills"][skill]["score"] == pytest.approx(50 - POINTS_PER_STAR, abs=0.2)
        assert ten["skills"][skill]["gap"] == pytest.approx(-5.1, abs=0.02)
        assert ten["skills"][skill]["score"] == 0
    assert at_comfort["effective"] == pytest.approx(4.9, abs=0.01)
    assert at_comfort["pass_chance"] == pytest.approx(PASS_AT_LEVEL, abs=0.01)
    assert ten["pass_chance"] < 0.01


def test_a_strong_skill_stays_strong_on_harder_maps_and_the_weak_one_limits():
    # twice the jump speed typical at 4.9★, a little slower tapping than typical
    levels = skill_levels(rows(4.9, {"aim": 2.0, "speed": 0.86, "stamina": 0.88}), 4.9)
    assert levels["aim"]["level"] > 8.0
    assert levels["speed"]["level"] < 4.9
    at_ten = compare_at(levels, 10.0)
    gap = {k: v["gap"] for k, v in at_ten["skills"].items()}
    assert gap["aim"] > gap["flow_aim"] > gap["speed"]  # the bars of the two weaker ones both clip at 0 here
    assert at_ten["skills"]["aim"]["score"] > 0
    assert at_ten["limiting"] in ("speed", "stamina")
    assert at_ten["effective"] < 4.9  # a weak skill that typical maps test pulls the effective level down


def test_the_pass_chance_falls_with_the_star_rating():
    levels = skill_levels(rows(6.0), 6.0)
    chances = [compare_at(levels, t)["pass_chance"] for t in (3.0, 5.0, 6.0, 7.0, 8.0, 10.0, 13.0)]
    assert chances == sorted(chances, reverse=True)
    assert chances[0] > 0.95 and chances[-1] < 1e-4


def test_accuracy_counts_for_its_bar_but_not_for_a_clean_pass():
    good, bad = (skill_levels(rows(6.0, {"accuracy": f}), 6.0) for f in (0.5, 2.0))
    assert good["accuracy"]["level"] > 6.0 > bad["accuracy"]["level"]
    assert compare_at(good, 7.0)["pass_chance"] == pytest.approx(compare_at(bad, 7.0)["pass_chance"])


def test_the_hit_error_spread_is_found_back_from_the_non_300_share():
    for sigma in (8.0, 15.0, 30.0):
        share = sum(w * math.erfc(win / (math.sqrt(2) * sigma)) for win, w in WINDOWS) / 2
        assert _sigma_for(share, WINDOWS) == pytest.approx(sigma, rel=1e-4)


def test_a_level_is_a_lower_bound_when_nothing_harder_was_played():
    # you held 98% of everything, and the hardest you played is about your level: harder may go as well
    levels = skill_levels(rows(5.0, success=0.98, tested=1.05), 5.0)
    assert levels["aim"]["bound"] == "at_least"
    assert levels["aim"]["tested"] == pytest.approx(5.0 + 0.0, abs=0.6)
    assert levels["reading"]["bound"] is None  # reading has no comparable hardest demand
    assert skill_levels(rows(5.0, success=0.98, tested=3.0), 5.0)["aim"]["bound"] is None


def test_skills_without_enough_data_or_comfort_have_no_level():
    r = rows(5.0, maps=2)
    r["accuracy"]["score"] = None
    levels = skill_levels(r, 5.0)
    assert levels["aim"] is None and levels["accuracy"] is None
    assert levels["stamina"] is not None
    assert all(v is None for v in skill_levels(rows(5.0), None).values())
    nothing = compare_at({k: None for k in SKILLS}, 6.0)
    assert nothing["effective"] is None and nothing["pass_chance"] is None


@pytest.mark.parametrize("comfort", [1.0, 4.9, 7.3, 11.4, 12.6, 13.0])
def test_the_star_ratings_to_compare_with(comfort):
    options = targets(comfort)
    assert options == sorted(options) and len(set(options)) == len(options)
    assert options[0] == 1.0 and options[-1] == 13.0
    assert round(comfort, 1) in options and default_target(comfort) in options
    gaps = [b - a for a, b in zip(options, options[1:], strict=False)]
    assert min(gaps) >= 0.1 - 1e-9
    assert all(g >= 0.5 - 1e-9 for a, g in zip(options, gaps, strict=False) if a > round(comfort, 1) + 2.0)
