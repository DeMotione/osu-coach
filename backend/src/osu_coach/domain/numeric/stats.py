"""Weighted statistics on numpy arrays."""

from __future__ import annotations

import math

import numpy as np


def weighted_quantile(values, weights, q: float) -> float:
    """The weighted ``q`` quantile of the finite values: the first value whose cumulative weight reaches ``q`` of
    the total (no interpolation); NaN without values."""
    v = np.asarray(values, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    ok = np.isfinite(v)
    v, w = v[ok], w[ok]
    if not len(v):
        return math.nan
    order = np.argsort(v)
    v, w = v[order], w[order]
    cw = np.cumsum(w)
    if cw[-1] <= 0:
        return math.nan
    return float(v[min(int(np.searchsorted(cw, q * cw[-1])), len(v) - 1)])
