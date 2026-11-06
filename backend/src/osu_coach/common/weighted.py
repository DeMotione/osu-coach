"""Weighted statistics on the pages' data frames (:mod:`osu_coach.common.frames`; column ``w`` is the replay weight)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from osu_coach.domain.numeric.stats import weighted_quantile


def played_notes(O: pd.DataFrame) -> pd.DataFrame:
    return O[(O["played"]) & (O["kind"] != "spinner")]


def weights_of(d: pd.DataFrame) -> pd.Series:
    """Replay weights of the rows (1 where there are none)."""
    if "w" in d:
        return d["w"].astype(float)
    return pd.Series(1.0, index=d.index)


def wrate(miss: pd.Series, w: pd.Series | None = None) -> float:
    if not len(miss):
        return math.nan
    if w is None:
        return float(miss.mean())
    s = float(w.sum())
    return float((miss.astype(float) * w).sum() / s) if s > 0 else math.nan


def wmean(x: pd.Series, w: pd.Series | None = None) -> float:
    ok = x.notna()
    if not ok.any():
        return math.nan
    if w is None:
        return float(x[ok].mean())
    ww = w[ok]
    s = float(ww.sum())
    return float((x[ok].astype(float) * ww).sum() / s) if s > 0 else math.nan


def wstd(x: pd.Series, w: pd.Series | None = None) -> float:
    ok = x.notna()
    if ok.sum() < 2:
        return math.nan
    xv = x[ok].astype(float).to_numpy()
    wv = np.ones(len(xv)) if w is None else w[ok].astype(float).to_numpy()
    s = wv.sum()
    if s <= 0:
        return math.nan
    m = (xv * wv).sum() / s
    return float(math.sqrt(max((wv * (xv - m) ** 2).sum() / s, 0.0)))


def wquantile(x: pd.Series, w: pd.Series | None, q: float) -> float:
    values = pd.to_numeric(x, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    return weighted_quantile(values, np.ones(len(values)) if w is None else w.to_numpy(dtype=float), q)
