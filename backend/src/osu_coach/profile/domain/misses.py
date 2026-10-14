"""Why misses happen, and the player's own miss model (miss chance against local difficulty)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from osu_coach.profile.domain.constants import FAST_JUMP_MS
from osu_coach.profile.domain.stats import _w


def fast_pattern(O: pd.DataFrame) -> pd.Series:
    """Bursts and streams (3+ notes at 1/4 or faster, any spacing) and very fast jumps (≤ 125 ms apart)."""
    fast = O["run_len"] >= 3 if "run_len" in O else pd.Series(False, index=O.index)
    if "pattern" in O and "dt_real" in O:
        fast = fast | (O["pattern"].isin(["jump", "spaced"]) & (O["dt_real"] <= FAST_JUMP_MS))
    return fast.fillna(False).astype(bool)


def miss_causes(O: pd.DataFrame) -> pd.Series:
    """The reason of every head miss, with aim misses split by pattern: ``speed_aim`` for aim misses on fast
    patterns (:func:`fast_pattern`) — the tap was in time but the cursor couldn't keep up with the tempo;
    ``aim`` for the rest (jumps at normal speed, single notes). Hits are None."""
    reason = O["miss_reason"] if "miss_reason" in O else pd.Series(None, index=O.index, dtype=object)
    cause = reason.where(~O["head_hit"].astype(bool), None).astype(object)
    cause[(cause == "aim") & fast_pattern(O)] = "speed_aim"
    return cause


# ------------------------------------------------------------------ expectation model
def fit_miss_model(df: pd.DataFrame, col: str = "local_eq"):
    """Logistic regression P(miss) = s(a + b*eq), weighted by ``w`` if present; returns predict(eq_array)."""
    d = df.dropna(subset=[col])
    y = (~d["head_hit"].astype(bool)).to_numpy(dtype=float)
    x = d[col].to_numpy(dtype=float)
    sw = _w(d).to_numpy(dtype=float)
    wsum = float(sw.sum())
    ymiss = float((y * sw).sum())
    base = ymiss / wsum if wsum > 0 else 0.05
    if len(d) < 50 or wsum < 50 or ymiss < 3 or ymiss > wsum - 3:
        return lambda e: np.full(np.shape(e), base)
    mu = float((x * sw).sum() / wsum)
    sd = float(math.sqrt((sw * (x - mu) ** 2).sum() / wsum)) or 1.0
    z = (x - mu) / sd
    X = np.column_stack([np.ones_like(z), z])
    w = np.array([math.log(max(base, 1e-3) / max(1 - base, 1e-3)), 0.0])
    lam = 1e-3
    for _ in range(50):
        p = _sigmoid(X @ w)
        g = X.T @ (sw * (p - y)) + lam * w
        H = X.T @ (X * (sw * p * (1 - p))[:, None]) + lam * np.eye(2)
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break

    def predict(e):
        e = (np.asarray(e, dtype=float) - mu) / sd
        return _sigmoid(w[0] + w[1] * e)

    predict.coef = (w[0], w[1], mu, sd)  # type: ignore[attr-defined]
    return predict


def _sigmoid(z):
    # clipped: extreme difficulty values must not overflow exp() (p is ~0 or ~1 there anyway)
    return 1 / (1 + np.exp(-np.clip(z, -35.0, 35.0)))


def _local_eq(O: pd.DataFrame) -> pd.Series:
    a = O["aim_eq"] if "aim_eq" in O else pd.Series(np.nan, index=O.index)
    s = O["speed_eq"] if "speed_eq" in O else pd.Series(np.nan, index=O.index)
    eq = pd.concat([a, s], axis=1).max(axis=1)
    if "stars" in O:
        eq = eq.fillna(O["stars"])
    return eq


def miss_chain_ratio(P: pd.DataFrame, window: int = 10) -> float:
    """Do misses make more misses? Observed / expected misses on the `window`
    notes after a miss, where "expected" comes from the player's own
    difficulty->miss model. Misses cluster in hard sections anyway; this ratio
    only rises above ~1 when a miss itself throws the player off (tilt, losing
    the rhythm). Notelock follow-ups are mechanical, so they are ignored."""
    if P.empty or "local_eq" not in P:
        return math.nan
    parts = []
    for _, d in P.groupby("replay_key", sort=False):
        is_nl = ((d["miss_reason"] == "notelock") & ~d["head_hit"].astype(bool)).to_numpy()
        prim = (~d["head_hit"].astype(bool)).to_numpy() & ~is_nl
        recent = pd.Series(prim.astype(float)).rolling(window, min_periods=1).max().shift(1).fillna(0).to_numpy()
        parts.append(pd.DataFrame({"local_eq": d["local_eq"].to_numpy(), "head_hit": ~prim,
                                   "after": recent > 0, "skip": is_nl, "w": _w(d).to_numpy()}))
    if not parts:
        return math.nan
    D = pd.concat(parts, ignore_index=True)
    D = D[~D["skip"]]
    fresh, after = D[~D["after"]], D[D["after"]]
    if len(after) < 20 or len(fresh) < 50 or after["w"].sum() < 20:
        return math.nan
    # expectation from notes with no recent miss, at the same local difficulty
    model = fit_miss_model(fresh)
    exp = float(np.nansum(model(after["local_eq"].to_numpy()) * after["w"].to_numpy()))
    obs = float(((~after["head_hit"]) * after["w"]).sum())
    if exp <= 0:
        return math.nan
    # shrink towards the typical value (~2x, median of real replays) so a handful of
    # misses can't produce extreme ratios: prior worth 5 expected misses
    return (obs + 5 * TYPICAL_CHAIN_RATIO) / (exp + 5)


TYPICAL_CHAIN_RATIO = 2.0
