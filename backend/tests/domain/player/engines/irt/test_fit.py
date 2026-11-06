"""The IRT fit: exact gradient, recovery of a simulated player, and failure reported instead of a number."""

import dataclasses
import math

import numpy as np
import pytest

from osu_coach.domain.player.engines.irt import constants as K
from osu_coach.domain.player.engines.irt import fit as F
from tests.domain.player.engines.irt.helpers import EPS, TRUE, simulate


def test_the_gradient_is_exact():
    d = F._data(simulate())
    rng = np.random.default_rng(3)
    d = dataclasses.replace(d, late=(rng.random(len(d.late)) < 0.3).astype(float))
    x = np.concatenate([rng.normal(6, 1, 6), [0.3, -6.0]])
    _, grad = F._objective(x, d, 6.0)
    h = 1e-5
    numeric = [(F._objective(x + e, d, 6.0)[0] - F._objective(x - e, d, 6.0)[0]) / (2 * h) for e in np.eye(8) * h]
    assert grad == pytest.approx(numeric, rel=1e-6, abs=1e-5)


@pytest.mark.parametrize("seed", [1, 2])
def test_a_simulated_player_is_recovered(seed):
    result = F.fit(simulate(seed=seed), prior=6.0)
    assert result.converged
    for k, true in TRUE.items():
        s = result.skills[k]
        assert abs(s.theta - true) < max(0.25, 3 * s.se), (k, s.theta, true, s.se)
    assert result.skills["acc"].theta == pytest.approx(6.0, abs=0.4)
    assert result.eps == pytest.approx(EPS, rel=0.6)


def test_fewer_misses_is_more_skill():
    groups = simulate()
    fewer = groups.replace(f_a=groups.f_a * 0.5, f_b=groups.f_b * 0.5, f_t=groups.f_t * 0.5)
    a, b = F.fit(groups, 6.0), F.fit(fewer, 6.0)
    for k in K.SKILLS:
        assert b.skills[k].theta > a.skills[k].theta, k


def test_a_skill_without_items_stays_at_the_prior_with_a_wide_range():
    groups = simulate()
    no_flow = groups.take(~np.isfinite(groups.b_flow))
    s = F.fit(no_flow, 6.0).skills["flow"]
    assert s.items == 0 and s.se > K.PROVISIONAL_SE


def test_a_fit_that_does_not_settle_gives_no_number(monkeypatch):
    monkeypatch.setattr(F, "_solve", lambda d, prior, x0, max_iter=100: (x0, -1.0, False, "stuck"))
    result = F.fit(simulate(), 6.0)
    assert not result.converged and result.skills == {}


def test_the_likelihood_alone_has_an_exact_gradient_too():
    # what the per-play (clustered) ranges are built from
    d = F._data(simulate())
    x = np.concatenate([np.full(6, 6.2), [0.1, -6.0]])
    _, grad = F._objective(x, d, 6.0, with_prior=False)
    h = 1e-5
    numeric = [
        (F._objective(x + e, d, 6.0, with_prior=False)[0] - F._objective(x - e, d, 6.0, with_prior=False)[0]) / (2 * h)
        for e in np.eye(8) * h
    ]
    assert grad == pytest.approx(numeric, rel=1e-6, abs=1e-5)


def test_slider_breaks_and_timing_are_never_random_lapses():
    # lapses are for note heads: with only sliders, the lapse rate has no say in the slider fit
    groups = simulate()
    sliders = groups.take(groups.kind == K.SLIDER)
    d = F._data(sliders)
    x_low, x_high = np.concatenate([np.full(6, 6.0), [0.0, -8.0]]), np.concatenate([np.full(6, 6.0), [0.0, -2.0]])
    ll_low, _ = F._objective(x_low, d, 6.0, with_prior=False)
    ll_high, _ = F._objective(x_high, d, 6.0, with_prior=False)
    assert ll_low == pytest.approx(ll_high)


def test_per_play_ranges_are_wider_than_the_pooled_ones():
    parts = [simulate(seed=s, n=300) for s in range(6)]
    from osu_coach.domain.player.engines.irt.items import group

    cols = {c: np.concatenate([getattr(g, c) for g in parts]) for c in parts[0].names()}
    late = cols.pop("late")
    merged = group(cols, late=late)
    pooled = F.fit(merged, 6.0)
    clustered = F.fit(merged, 6.0, parts=parts)
    for i, k in enumerate(("aim", "flow", "tap", "stam", "read", "sl")):
        model = math.sqrt(pooled.cov[i, i] / K.D)  # the curvature's own SE (pooled.cov holds D × it)
        assert clustered.skills[k].se >= math.sqrt(K.D_CLUSTER) * model * 0.999, k
