"""pp-style rank weighting of a skill's values: the hardest plays count most."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def rank_weights(n_total: int, count: int) -> np.ndarray:
    """Weights of ``count`` plays sorted hardest / best first, like osu!'s pp list but linear: the first counts
    100%, each next one 1/``n_total`` less (100 replays analysed: 100%, 99%, 98%, ...; 50 replays: 2% steps)."""
    n_total = max(int(n_total), 1)
    return np.clip(1.0 - np.arange(count) / n_total, 0.0, 1.0)


def ranked_mean(values, n_total: int) -> float:
    """Weighted average of per-play values, highest first, with :func:`rank_weights`."""
    v = np.sort(np.asarray([x for x in values if x is not None and np.isfinite(x)], dtype=float))[::-1]
    if not len(v):
        return math.nan
    w = rank_weights(n_total, len(v))
    return float((v * w).sum() / w.sum()) if w.sum() > 0 else math.nan


def _n_replays(P: pd.DataFrame) -> int:
    return int(P["replay_key"].nunique()) if "replay_key" in P and len(P) else 1


def difficulty_weights(
    P: pd.DataFrame, mask: pd.Series | None, col: str = "local_eq", n_total: int | None = None
) -> pd.Series:
    """Per-row weights for one skill: its plays ranked by how hard that skill's notes were in them (the 80th
    percentile of ``col`` on the notes in ``mask``; plays without such notes by star rating), hardest = 100%,
    then 1/n less per place (:func:`rank_weights`)."""
    if P.empty:
        return pd.Series(dtype=float)
    key = P["replay_key"] if "replay_key" in P else pd.Series("all", index=P.index)
    src = P[col] if col in P else P.get("local_eq", pd.Series(np.nan, index=P.index))
    d = src.where(mask, np.nan) if mask is not None else src
    hard = d.groupby(key).quantile(0.8)
    if "stars" in P:
        hard = hard.fillna(P["stars"].groupby(key).first())
    hard = hard.fillna(0.0).sort_values(ascending=False)
    w = dict(zip(hard.index, rank_weights(n_total or len(hard), len(hard))))
    return key.map(w).astype(float).fillna(0.0)


def _weighted(P: pd.DataFrame, weights: pd.Series) -> pd.DataFrame:
    Q = P.copy()
    Q["w"] = weights
    return Q
