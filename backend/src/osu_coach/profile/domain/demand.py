"""What maps of a star rating demand of each skill, and the star rating a skill corresponds to.

The demand curves are fitted on the bundled ranked map pool (:func:`fit_demand`, run by
``backend/tools/fit_demand_curves.py``, which writes :mod:`demand_table`): for every star rating on a grid, the
median of each skill's demand over the maps around it — no-mod maps plus the same maps with DT (1.5x the speed: BPM
and real-time velocities x1.5, hit windows and approach time /1.5, star rating with DT), which reaches ~14★. Demands
are log2 values, so only their differences matter: +1 = twice as demanding.

Only the shape of the curves is used (how much more a harder map demands); the player's own measurements anchor
them at the comfort level (:mod:`readiness`). The pool's map statistics are close to, not the same as, the ones a
player's values are measured with (e.g. the median jump instead of the 30 fastest), which changes the level of a
curve much more than its shape.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

SKILLS = ("aim", "flow_aim", "speed", "stamina", "accuracy", "sliders", "reading")
GRID = np.arange(1.0, 13.01, 0.25)  # ★
WINDOW = 0.5  # ★ either side of a grid point whose maps make its median
MIN_MAPS = 15  # a grid point needs this many maps, the others are interpolated
MIN_SLOPE = 1 / 16  # log2 per ★: the curves rise at least this fast (x2 per 16★), so a level stays well defined
DT = 1.5


def _preempt_ms(ar: pd.Series) -> pd.Series:
    """How long a note is visible before it has to be hit (osu!'s approach rate)."""
    return pd.Series(np.where(ar < 5, 1200 + 600 * (5 - ar) / 5, 1200 - 750 * (ar - 5) / 5), index=ar.index)


def _map_demands(pool: pd.DataFrame, rate: float) -> pd.DataFrame:
    """log2 demand of every skill on every map of the pool at a playback ``rate`` (1 = no mod, 1.5 = DT)."""
    stars = pool["stars_dt"] if rate != 1.0 else pool["stars"]
    diameter = 2 * (54.4 - 4.48 * pool["cs"]).clip(lower=1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        aim = np.log2(pool["jump_velocity"] * rate * 1000 / diameter)  # cursor speed of jumps, circle widths / s
        speed = np.log2(np.fmax(pool["stream_bpm"], pool["burst_bpm"]) * rate)  # tempo of bursts and streams
        sliders = np.log2(pool["slider_velocity"] * rate * 1000 / diameter)  # slider speed, circle widths / s
        window = np.log2((79.5 - 6 * pool["od"]).clip(lower=1.0) / rate)  # the 300 window, ms (real time)
        preempt = np.log2(_preempt_ms(pool["ar"]) / rate)  # time a note is visible, ms (real time)
    out = pd.DataFrame(
        {
            "stars": stars,
            "aim": aim,
            "speed": speed,
            "stamina": speed,  # holding a tempo: grows like the tempo itself
            "flow_aim": (aim + speed) / 2,  # spaced streams: spacing x tempo (no flow statistic in the pool)
            "accuracy": -window,  # a smaller window demands more precision
            "sliders": sliders,
            "reading": -preempt,  # notes that appear later demand faster reading
        }
    )
    return out.replace([np.inf, -np.inf], np.nan)


def fit_demand(pool: pd.DataFrame) -> dict:
    """Demand curves (log2, rising with the star rating) and how much maps test each skill, on :data:`GRID`."""
    maps = pd.concat([_map_demands(pool, 1.0), _map_demands(pool, DT)], ignore_index=True).dropna(subset=["stars"])
    curves = {}
    for skill in SKILLS:
        d = maps[["stars", skill]].dropna()
        med = []
        for g in GRID:
            near = d[(d["stars"] >= g - WINDOW) & (d["stars"] < g + WINDOW)][skill]
            med.append(float(near.median()) if len(near) >= MIN_MAPS else math.nan)
        y = pd.Series(med).interpolate(limit_direction="both").to_numpy(dtype=float, copy=True)
        for i in range(1, len(y)):  # never falls, and rises at least MIN_SLOPE per ★
            y[i] = max(y[i], y[i - 1] + MIN_SLOPE * (GRID[i] - GRID[i - 1]))
        curves[skill] = [round(float(v - y[0]), 4) for v in y]  # relative to 1★: only differences matter
    # how much the maps around each star rating test a skill (the pool's 0-1 skill weights, no-mod maps)
    tests = {}
    nm = pool.dropna(subset=["stars"])
    for skill in SKILLS:
        col = f"s_{skill}"
        vals = []
        for g in GRID:
            near = nm[(nm["stars"] >= g - WINDOW) & (nm["stars"] < g + WINDOW)][col].dropna() if col in nm else []
            vals.append(float(near.mean()) if len(near) >= MIN_MAPS else math.nan)
        tests[skill] = [round(float(v), 3) for v in pd.Series(vals).interpolate(limit_direction="both").to_numpy()]
    return {"grid": [float(g) for g in GRID], "demand": curves, "tests": tests, "maps": int(len(pool))}


# ------------------------------------------------------------------ lookups on the fitted table
def _table():
    # imported when first used: fit_demand (which writes the table) works without it
    from osu_coach.profile.domain import demand_table

    return demand_table


def log_demand(skill: str, stars: float) -> float:
    """log2 demand of ``skill`` on typical maps of ``stars`` (clamped to the table's 1–13★)."""
    table = _table()
    return float(np.interp(stars, table.GRID, table.DEMAND[skill]))


def stars_for(skill: str, demand: float) -> tuple[float, bool]:
    """The star rating whose typical maps demand ``demand`` (log2) of ``skill``, and whether it is beyond the
    table (then the table's lowest / highest star rating is returned)."""
    table = _table()
    curve = np.asarray(table.DEMAND[skill], dtype=float)
    if demand < curve[0]:
        return float(table.GRID[0]), True
    if demand > curve[-1]:
        return float(table.GRID[-1]), True
    return float(np.interp(demand, curve, table.GRID)), False


def skill_weights(stars: float) -> dict[str, float]:
    """How much typical maps of ``stars`` test each skill (0–1), held flat beyond the pool's star ratings."""
    table = _table()
    return {s: float(np.interp(stars, table.GRID, table.TESTS[s])) for s in SKILLS}
