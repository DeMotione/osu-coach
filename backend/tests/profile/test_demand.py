"""Skill demand curves: fitted on the bundled map pool, rising with the star rating, invertible."""

import numpy as np
import pytest

from osu_coach.maps.repository import load_pool
from osu_coach.profile.domain import demand_table
from osu_coach.profile.domain.demand import MIN_SLOPE, SKILLS, fit_demand, log_demand


def test_the_table_is_fitted_on_the_bundled_pool():
    # stale after the pool changes: run backend/tools/fit_demand_curves.py
    fit = fit_demand(load_pool())
    assert fit["grid"] == demand_table.GRID
    for skill in SKILLS:
        assert fit["demand"][skill] == pytest.approx(demand_table.DEMAND[skill], abs=1e-4), skill


@pytest.mark.parametrize("skill", SKILLS)
def test_harder_maps_always_demand_more(skill):
    curve = np.asarray(demand_table.DEMAND[skill])
    steps = np.diff(curve) / np.diff(demand_table.GRID)
    assert curve[0] == 0
    assert (steps >= MIN_SLOPE - 1e-3).all()  # the table is rounded to 4 decimals
    assert log_demand(skill, 0.5) == 0 and log_demand(skill, 14) == curve[-1]  # held flat beyond the table


@pytest.mark.parametrize("skill", SKILLS)
def test_the_curves_have_no_steps(skill):
    # DT maps entering the pool around 7-8★ make the raw medians jump: the slopes are smoothed over ±1★
    steps = np.diff(demand_table.DEMAND[skill])
    assert np.abs(np.diff(steps)).max() < 0.05


def test_typical_maps_of_10_stars_demand_much_more_than_of_5():
    # cursor speed of jumps roughly doubles from 5 to 10★, the tempo of streams grows by about half
    assert 0.8 < log_demand("aim", 10) - log_demand("aim", 5) < 1.6
    assert 0.4 < log_demand("speed", 10) - log_demand("speed", 5) < 0.9
