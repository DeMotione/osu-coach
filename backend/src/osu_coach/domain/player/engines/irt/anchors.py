"""The star scale: anchor curves from a raw demand to stars (fitted on the map pool), and back to natural units."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np

GRID = np.arange(1.0, 13.001, 0.25)  # ★ (49 knots)
WINDOW = 0.5  # ★ either side of a knot whose maps make its median
MIN_ROWS = 15  # a knot needs this many maps, the others are interpolated
STEP = 1 / 64  # the curves rise at least this much per knot
DT = 1.5
ANCHORED = ("aim", "spd", "read", "acc", "sl")
LOGGED = ("aim", "spd")  # medians of a rating, used as log2 (the others are log2 values already)
# natural units of each skill's translation: what the median pool map at a star rating demands
UNITS = {"aim": "d/s", "spd": "BPM", "read": "AR", "acc": "OD", "sl": "d/s"}


def preempt_ms(ar: np.ndarray | float) -> np.ndarray:
    """How long a note is visible before it has to be hit (ms) at this approach rate."""
    ar = np.asarray(ar, dtype=float)
    return np.where(ar >= 5, 1200 - 150 * (ar - 5), 1200 + 120 * (5 - ar))


def ar_of_preempt(p: np.ndarray | float) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    return np.where(p <= 1200, 5 + (1200 - p) / 150, 5 - (p - 1200) / 120)


def pool_rows(pool: Mapping[str, Any]) -> dict[str, np.ndarray]:
    """The pool's maps as NM and DT rows: star rating, rate, the raw demands ``u_*`` of §6.1 and the natural units of
    §6.7 (columns by name, NM rows first)."""

    def col(name: str) -> np.ndarray:
        return np.asarray(pool[name], dtype=float)

    stars, stars_dt = col("stars"), col("stars_dt")
    out: dict[str, list[np.ndarray]] = {}
    for rate in (1.0, DT):
        s = stars if rate == 1.0 else stars_dt
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(stars > 0, stars_dt / stars, np.nan) if rate != 1.0 else np.ones_like(stars)
            diam = 2 * np.maximum(54.4 - 4.48 * col("cs"), 1.0)
            preempt = preempt_ms(col("ar")) / rate
            window = np.maximum(79.5 - 6 * col("od"), 1.0) / rate
            rows = {
                "stars": s,
                "rate": np.full_like(s, rate),
                "u_aim": col("aim") * r,
                "u_spd": col("speed") * r,
                "u_read": -np.log2(preempt),
                "u_acc": -np.log2(window),
                "u_sl": np.log2(col("slider_velocity") * rate * 1000 / diam),
                "n_aim": col("jump_velocity") * rate * 1000 / diam,
                "n_spd": np.fmax(col("stream_bpm"), col("burst_bpm")) * rate,
                "n_read": ar_of_preempt(preempt),
                "n_acc": (79.5 - window) / 6,
                "n_sl": col("slider_velocity") * rate * 1000 / diam,
            }
        for k, v in rows.items():
            out.setdefault(k, []).append(np.where(np.isfinite(v), v, np.nan))
    return {k: np.concatenate(v) for k, v in out.items()}


def _medians(stars: np.ndarray, values: np.ndarray, rising: bool = True) -> np.ndarray:
    """Median of ``values`` around every knot (gaps interpolated, ends held), made to rise by at least
    :data:`STEP` per knot (or fall, for ``rising=False``)."""
    ok = np.isfinite(stars) & np.isfinite(values)
    s, v = stars[ok], values[ok]
    med = []
    for g in GRID:
        near = v[(s >= g - WINDOW) & (s < g + WINDOW)]
        med.append(float(np.median(near)) if len(near) >= MIN_ROWS else math.nan)
    y = np.asarray(med)
    idx = np.arange(len(y))
    known = np.isfinite(y)
    y = np.interp(idx, idx[known], y[known])
    sign = 1.0 if rising else -1.0
    for i in range(1, len(y)):
        y[i] = sign * max(sign * y[i], sign * y[i - 1] + STEP)
    return y


def fit_anchors(pool: Mapping[str, Any]) -> dict:
    """The anchor knots ``X_k`` (raw demand at every knot of :data:`GRID`, log2 for aim and speed) and the natural
    units at every knot, from the pool's columns."""
    rows = pool_rows(pool)
    anchors, natural = {}, {}
    for k in ANCHORED:
        kappa = _medians(rows["stars"], rows[f"u_{k}"])
        x = np.log2(kappa) if k in LOGGED else kappa
        anchors[k] = [round(float(v), 5) for v in x]
        natural[k] = [round(float(v), 4) for v in _medians(rows["stars"], rows[f"n_{k}"], rising=True)]
    return {"grid": [float(g) for g in GRID], "anchors": anchors, "natural": natural, "maps": len(pool["stars"])}


def star_of(x: np.ndarray | float, knots: np.ndarray, grid: np.ndarray = GRID) -> np.ndarray:
    """``S_k``: stars of the raw demand ``x`` (on the knots' scale), linear between knots and extrapolated beyond
    them with the slope of the last two stars (no ceiling, no floor)."""
    x = np.asarray(x, dtype=float)
    knots = np.asarray(knots, dtype=float)
    hi_slope = (grid[-1] - grid[-9]) / (knots[-1] - knots[-9])  # 13★ vs 11★
    lo_slope = (grid[8] - grid[0]) / (knots[8] - knots[0])  # 3★ vs 1★
    out = np.interp(x, knots, grid)
    out = np.where(x > knots[-1], grid[-1] + (x - knots[-1]) * hi_slope, out)
    return np.where(x < knots[0], grid[0] + (x - knots[0]) * lo_slope, out)


def natural_at(theta: float, values: np.ndarray, grid: np.ndarray = GRID) -> float:
    """The natural-unit demand of the median pool map at ``theta`` ★ (held flat beyond the grid)."""
    return float(np.interp(theta, grid, np.asarray(values, dtype=float)))
