"""Experimental skillset recommendation: the score F(m) of the suggested maps."""

import pytest

from osu_coach.maps.repository import POOL_PATH, load_pool
from osu_coach.maps.skillset import recommend

pytestmark = pytest.mark.skipif(not POOL_PATH.exists(), reason="bundled pool not built")


OFFSETS = {"Warm-up": -15, "Comfort": -5, "Push": 5}


@pytest.mark.parametrize("theta", [2.5, 4.39, 6.5])
@pytest.mark.parametrize("ability", [0.0, 100.0])
def test_the_best_map_scores_near_zero_for_any_rating(theta, ability):
    """A rating far from 50 asks for demands no map at the target stars has; the best of them still scores near 0
    (#33: at 4.4★ with accuracy 0, the best map scored -1.78, every other one lower)."""
    result = recommend(load_pool(), theta, {"accuracy": ability}, "accuracy", ("accuracy",))
    for goal, stage in result["goals"].items():
        best = stage["maps"][0]
        b = best["breakdown"]
        assert best["formula_score"] > -1, (goal, b["terms"])
        assert b["target_demand"] == stage["target_demand"] == ability + OFFSETS[goal]  # what the rating asks for
        lowest = min(m["skill_demand"] for m in stage["maps"])
        highest = max(m["skill_demand"] for m in stage["maps"])
        assert b["reachable_demand"] == min(max(b["target_demand"], lowest), highest)


def test_a_reachable_target_is_used_as_it_is():
    stage = recommend(load_pool(), 4.39, {"accuracy": 50.0}, "accuracy", ("accuracy",))["goals"]["Comfort"]
    assert all(m["breakdown"]["reachable_demand"] == m["breakdown"]["target_demand"] == 45 for m in stage["maps"])


def test_weak_other_skills_only_count_beyond_what_every_map_asks():
    """Three weak skills, as Skill Development assesses them: no map at these stars spares the other two, so only the
    overload beyond the least any of them asks is a risk."""
    abilities = {"accuracy": 0.0, "aim": 10.0, "speed": 20.0}
    for skill in abilities:
        result = recommend(load_pool(), 4.39, abilities, skill, tuple(abilities))
        for goal, stage in result["goals"].items():
            best = stage["maps"][0]
            assert best["formula_score"] > -1, (skill, goal, best["breakdown"]["terms"])
            for part in best["breakdown"]["bottlenecks"]:
                floor = max(part["ability"] + part["margin"], part["least_demand"])
                assert part["overload"] == pytest.approx(max(0.0, part["demand"] - floor))


def test_a_widened_star_window_is_scored_as_wide():
    """Few timing maps at low stars: the window widens, and so does the star term's scale."""
    warmup = recommend(load_pool(), 2.5, {"accuracy": 0.0}, "accuracy", ("accuracy",))["goals"]["Warm-up"]
    b = warmup["maps"][0]["breakdown"]
    assert b["star_window"] > 0.2 and b["star_scale"] == pytest.approx(b["star_window"])
    assert b["terms"]["stars"] > -1
