"""Weighted statistics shared by all the profile modules (column ``w`` is the replay weight)."""
from __future__ import annotations

import math
import numpy as np
import pandas as pd

from osu_coach.profile.domain.constants import FEW_MISSES


def played_notes(O: pd.DataFrame) -> pd.DataFrame:
    return O[(O["played"]) & (O["kind"] != "spinner")]


def _w(d: pd.DataFrame) -> pd.Series:
    """Replay weights of the rows (1 where there are none)."""
    if "w" in d:
        return d["w"].astype(float)
    return pd.Series(1.0, index=d.index)


def _rate(miss: pd.Series, w: pd.Series | None = None) -> float:
    if not len(miss):
        return math.nan
    if w is None:
        return float(miss.mean())
    s = float(w.sum())
    return float((miss.astype(float) * w).sum() / s) if s > 0 else math.nan


def _wmean(x: pd.Series, w: pd.Series | None = None) -> float:
    ok = x.notna()
    if not ok.any():
        return math.nan
    if w is None:
        return float(x[ok].mean())
    ww = w[ok]
    s = float(ww.sum())
    return float((x[ok].astype(float) * ww).sum() / s) if s > 0 else math.nan


def _wstd(x: pd.Series, w: pd.Series | None = None) -> float:
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


def _wquantile(x: pd.Series, w: pd.Series | None, q: float) -> float:
    ok = x.notna() & np.isfinite(pd.to_numeric(x, errors="coerce").astype(float))
    if not ok.any():
        return math.nan
    xv = x[ok].astype(float).to_numpy()
    wv = np.ones(len(xv)) if w is None else w[ok].astype(float).to_numpy()
    order = np.argsort(xv)
    xv, wv = xv[order], wv[order]
    cw = np.cumsum(wv)
    if cw[-1] <= 0:
        return math.nan
    i = int(np.searchsorted(cw, q * cw[-1]))
    return float(xv[min(i, len(xv) - 1)])


def _ur(errs: pd.Series, w: pd.Series | None = None) -> float:
    errs = errs.dropna()
    if len(errs) <= 5:
        return math.nan
    if w is None:
        return float(10 * errs.std(ddof=0))
    return 10 * _wstd(errs, w.loc[errs.index])


def _n(d: pd.DataFrame) -> float:
    """Weighted number of rows (= rows when unweighted)."""
    return float(_w(d).sum())


def _clip(v, lo=0.0, hi=100.0):
    return float(min(hi, max(lo, v)))


def _score_from_ratio(expected: float, observed: float) -> float:
    """50 = as expected, each halving of misses vs expectation = +35."""
    expected = max(expected, 1e-6)
    observed = max(observed, 0.5)  # Laplace-ish floor, avoids infinite scores
    return _clip(50 + 35 * math.log2(expected / observed))


def _subset_score(P: pd.DataFrame, mask: pd.Series, model, min_n: int = 60) -> dict:
    d = P[mask]
    if len(d) == 0:
        return {"score": None, "n": 0, "observed": 0, "expected": 0}
    W = _w(d)
    n = float(W.sum())
    obs = float(((~d["head_hit"]) * W).sum())
    exp = float(np.nansum(model(d["local_eq"].to_numpy()) * W.to_numpy()))
    score = _score_from_ratio(exp, obs) if (n >= min_n and exp >= 3) else None
    out = {"score": score, "n": int(round(n)), "observed": obs, "expected": exp,
           "miss_rate": obs / n if n > 0 else math.nan, "ratio": obs / exp if exp > 0 else math.nan}
    if score is None and n >= min_n and obs < FEW_MISSES and exp < FEW_MISSES:
        # enough notes, but you (almost) never miss: the score compares misses, so there's nothing to compare
        out["too_few_misses"] = True
    return out


def _map_key(P: pd.DataFrame) -> pd.Series:
    """Beatmap (and rate) of each row, so repeated plays of one map count once; the replay when unknown."""
    key = P["replay_key"].astype(str) if "replay_key" in P else pd.Series("all", index=P.index)
    if "map_md5" in P:
        rate = P["rate"].astype(float).fillna(1.0).round(3).astype(str) if "rate" in P else ""
        return P["map_md5"].fillna(key).astype(str) + "@" + rate
    return key


def _dur(W: float) -> str:
    return f"{W:.0f} s" if W < 60 else f"{W / 60:.0f} min"
