"""The IRT fit: exact gradient, recovery of a simulated player, and failure reported instead of a number."""

import numpy as np
import pytest

from osu_coach.domain.player.engines.irt import constants as K
from osu_coach.domain.player.engines.irt import fit as F
from tests.domain.player.engines.irt.helpers import EPS, TRUE, simulate


def test_the_gradient_is_exact():
    d = F._data(simulate())
    rng = np.random.default_rng(3)
    d = F._Data(d.b, d.mask, (rng.random(len(d.late)) < 0.3).astype(float), d.n, d.f, d.mix)
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
