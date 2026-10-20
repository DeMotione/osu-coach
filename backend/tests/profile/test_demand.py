"""Skill demand curves: fitted on the bundled map pool, rising with the star rating, invertible."""

import numpy as np
import pytest

from osu_coach.maps.repository import load_pool
from osu_coach.profile.domain import demand_table
from osu_coach.profile.domain.demand import MIN_SLOPE, SKILLS, fit_demand, log_demand, skill_weights, stars_for


def test_the_table_is_fitted_on_the_bundled_pool():
    # stale after the pool changes: run backend/tools/fit_demand_curves.py
    fit = fit_demand(load_pool())
    assert fit["grid"] == demand_table.GRID
    for skill in SKILLS:
        assert fit["demand"][skill] == pytest.approx(demand_table.DEMAND[skill], abs=1e-4), skill
        assert fit["tests"][skill] == pytest.approx(demand_table.TESTS[skill], abs=1e-3), skill


@pytest.mark.parametrize("skill", SKILLS)
def test_harder_maps_always_demand_more(skill):
    curve = np.asarray(demand_table.DEMAND[skill])
    steps = np.diff(curve) / np.diff(demand_table.GRID)
    assert curve[0] == 0
    assert (steps >= MIN_SLOPE - 1e-3).all()  # the table is rounded to 4 decimals


def test_typical_maps_of_10_stars_demand_much_more_than_of_5():
    # cursor speed of jumps roughly doubles from 5 to 10★, the tempo of streams grows by about half
    assert 0.8 < log_demand("aim", 10) - log_demand("aim", 5) < 1.6
    assert 0.4 < log_demand("speed", 10) - log_demand("speed", 5) < 0.9


@pytest.mark.parametrize("skill", SKILLS)
@pytest.mark.parametrize("stars", [1.0, 3.3, 6.0, 9.75, 13.0])
def test_a_demand_gives_back_its_star_rating(skill, stars):
    level, beyond = stars_for(skill, log_demand(skill, stars))
    assert level == pytest.approx(stars, abs=1e-6)
    assert not beyond


def test_demands_beyond_the_table_are_marked():
    top = demand_table.DEMAND["aim"][-1]
    assert stars_for("aim", top + 1) == (13.0, True)
    assert stars_for("aim", -1) == (1.0, True)


def test_how_much_maps_test_each_skill():
    w5, w10 = skill_weights(5), skill_weights(10)
    assert all(0 <= v <= 1 for v in (*w5.values(), *w10.values()))
    assert w10["speed"] > w5["speed"]  # harder maps have more streams
    assert w5["aim"] > w5["stamina"]
