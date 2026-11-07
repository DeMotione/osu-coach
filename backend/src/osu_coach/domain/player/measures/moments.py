"""Count, sum and sum of squares of values, and the weighted mean / spread of several such sets (one per play)."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class Moments:
    """Count, sum and sum of squares of some values (missing ones left out)."""

    n: int = 0
    total: float = 0.0
    squares: float = 0.0

    @classmethod
    def of(cls, values: np.ndarray) -> Moments:
        v = np.asarray(values, dtype=np.float64)
        v = v[~np.isnan(v)]
        return cls(len(v), float(v.sum()), float((v * v).sum()))


def weighted_std(parts: Iterable[tuple[Moments, float]]) -> tuple[float, int]:
    """The weighted standard deviation (population) of the values behind these moments, each set with one weight,
    and how many values there are."""
    sw = swx = swxx = 0.0
    count = 0
    for m, w in parts:
        sw += w * m.n
        swx += w * m.total
        swxx += w * m.squares
        count += m.n
    if count < 2 or sw <= 0:
        return math.nan, count
    mean = swx / sw
    return math.sqrt(max(swxx / sw - mean * mean, 0.0)), count


def weighted_mean(parts: Iterable[tuple[Moments, float]]) -> float:
    sw = swx = 0.0
    for m, w in parts:
        sw += w * m.n
        swx += w * m.total
    return swx / sw if sw > 0 else math.nan
