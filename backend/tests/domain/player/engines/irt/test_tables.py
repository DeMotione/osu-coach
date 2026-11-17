"""The star scale: fitted on the bundled pool, rising, and the spec's own examples."""

import numpy as np
import pytest

from osu_coach.domain.player.engines.irt import tables
from osu_coach.domain.player.engines.irt.anchors import ANCHORED, fit_anchors, preempt_ms, star_of
from osu_coach.infra.map_pool import load_pool


def test_the_tables_are_fitted_on_the_bundled_pool():
    # stale after the pool changes: run backend/tools/build_irt_tables.py
    fit = fit_anchors(load_pool())
    for k in ANCHORED:
        assert fit["anchors"][k] == pytest.approx(tables.ANCHORS[k], abs=1e-4), k
        assert fit["natural"][k] == pytest.approx(tables.NATURAL[k], abs=1e-3), k


@pytest.mark.parametrize("skill", ANCHORED)
def test_anchors_rise_and_have_no_ceiling(skill):
    knots = np.asarray(tables.ANCHORS[skill])
    assert (np.diff(knots) > 0).all()
    assert star_of(knots[-1] + 1, knots) > 13 and star_of(knots[0] - 1, knots) < 1


def test_the_specs_examples():
    # on the 50k pool (docs/star-scale-irt.md, decision 25); the spec's own pool gave 5.66, 5.85 and 5.5 / 7.75 / 8.0
    assert star_of(np.log2(3.0), tables.ANCHORS["aim"]) == pytest.approx(5.71, abs=0.01)
    assert star_of(np.log2(2.5), tables.ANCHORS["spd"]) == pytest.approx(5.72, abs=0.01)
    for ar, stars in ((9.3, 5.73), (10, 6.93), (10.33, 7.25)):
        assert star_of(-np.log2(preempt_ms(ar)), tables.ANCHORS["read"]) == pytest.approx(stars, abs=0.01)
