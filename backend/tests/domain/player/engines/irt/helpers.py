"""A simulated player for the IRT tests: groups drawn from the model itself, with known abilities."""

import numpy as np

from osu_coach.domain.player.engines.irt import constants as K
from osu_coach.domain.player.engines.irt.items import B_COLUMNS, IrtGroups

TRUE = {"aim": 6.6, "flow": 6.1, "tap": 6.2, "stam": 5.3, "read": 7.0, "sl": 5.6}
EPS = 0.0015


def _sigmoid(z):
    return 1 / (1 + np.exp(-z))


def simulate(theta=TRUE, eps=EPS, n=1500, seed=1, offsets=(-2, -1, -0.5, 0, 0.5, 1, 1.5), acc_theta=6.0):
    """Head groups of every class at difficulties around the true abilities, slider and accuracy groups."""
    rng = np.random.default_rng(seed)
    t = np.array([theta[k] for k in K.SKILLS])
    rows = []
    classes = [("aim",), ("tap",), ("stam",), ("flow", "tap")]
    for skills in classes:
        for off in offsets:
            for roff in (-1.5, -0.5, 0.5):
                b = np.full(6, np.nan)
                for s in skills:
                    b[K.SKILLS.index(s)] = theta[s] + off
                b[K.SKILLS.index("read")] = theta["read"] + roff
                rows.append((K.HEAD, b))
    for off in offsets:
        b = np.full(6, np.nan)
        b[K.SKILLS.index("sl")] = theta["sl"] + off
        rows.append((K.SLIDER, b))
    cols = {c: [] for c in IrtGroups.names()}
    for kind, b in rows:
        m = np.isfinite(b)
        q = np.where(m, _sigmoid(-(K.C + K.A * (t - np.nan_to_num(b)))), 0.0)
        p = (1 - eps) * np.prod(1 - q)
        misses = rng.binomial(n, 1 - p)
        if kind == K.HEAD:
            mix = eps * K.E0 + q @ K.E
            f = rng.multinomial(misses, mix / mix.sum())
        else:
            f = np.array([misses, 0, 0])
        for c, v in zip(B_COLUMNS, b, strict=True):
            cols[c].append(v)
        cols["kind"].append(kind)
        cols["b_acc"].append(np.nan)
        cols["late"].append(0.0)
        cols["n"].append(float(n))
        for c, v in zip(("f_a", "f_b", "f_t"), f, strict=True):
            cols[c].append(float(v))
    for off in offsets:  # accuracy
        b_acc = acc_theta + off
        q = _sigmoid(-(K.C_ACC + K.A_ACC * (acc_theta - b_acc)))
        for c in B_COLUMNS:
            cols[c].append(np.nan)
        cols["kind"].append(K.ACCURACY)
        cols["b_acc"].append(b_acc)
        cols["late"].append(0.0)
        cols["n"].append(float(n))
        cols["f_a"].append(float(rng.binomial(n, q)))
        cols["f_b"].append(0.0)
        cols["f_t"].append(0.0)
    return IrtGroups.from_columns({k: np.asarray(v) for k, v in cols.items()})
