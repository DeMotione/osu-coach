"""The pool's maps in a goal's configurations, as the rows the play goals rank (``domain.play_goals.recommend``).

They come from the pool's map table (``infra.variant_table``: every pool map with HD, HR and DT at every speed from
1.10 to 2.00) and, for Farm PP, its pp table (``infra.pp_table``): no .osu file and no calculation. A configuration's
maps are looked at as arrays, only those in its star window (``recommend.level``); the ``LIMIT`` most promising are
made into rows: Farm PP's with the most pp at the accuracy their difficulty asks for, the other goals' nearest the
level, and with skills in focus, the ones training them most (the ranking's own terms, without the player's plays).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from osu_coach.domain.maps.variants import VariantTable, configuration_columns, pool_maps, relevance, rows_at
from osu_coach.domain.play_goals.pool import ACCURACIES, CONFIGS, standard_rate
from osu_coach.domain.play_goals.recommend import Level, practice_scale
from osu_coach.infra.pp_table import MISSING, PpTable

LIMIT = 600  # configurations made into rows
FARMABLE = ("ranked", "approved")
# what relevance (suggestions.skill_scores on columns) reads
RELEVANCE_COLUMNS = (
    "aim",
    "speed",
    "jump_share",
    "spaced_share",
    "spaced_stream_share",
    "stream_share",
    "burst_share",
    "stream_notes",
    "max_run",
    "drain_length",
    "od",
    "circle_share",
    "slider_share",
    "slider_factor",
    "reverse_share",
    "density_p90",
    "odd_rhythm_share",
    "evenness",
)


@dataclass(frozen=True)
class Wanted:
    """A configuration a goal's maps are played in, and the level they are picked around in it."""

    config: str  # pool.config_key
    mods: str  # the combination (a CONFIGS name)
    rate: float
    level: Level


def candidates(
    table: VariantTable,
    pool: pd.DataFrame,
    pp: PpTable | None,
    wanted: Sequence[Wanted],
    client: str,
    goal: str,
    focus: Sequence[str],
    limit: int = LIMIT,
) -> list[dict]:
    """The rows of the pool's most promising maps in the ``wanted`` configurations (Farm PP: only ranked and approved
    maps, in combinations at their own speed, with their pp curves from ``pp``)."""
    maps, record_of = pool_maps(table, pool["md5"].astype(str).tolist())
    nm = pool["stars"].to_numpy(dtype=float, na_value=np.nan)[record_of[maps]]
    farmable = pool["status"].isin(FARMABLE).to_numpy()[record_of[maps]]
    found: list[tuple[np.ndarray, int, np.ndarray]] = []  # (how promising, wanted index, table maps)
    for w, want in enumerate(wanted):
        hr, hd = "HR" in want.mods, "HD" in want.mods
        lv = want.level
        stars = configuration_columns(table, maps, hr, hd, want.rate, ("stars",))["stars"]
        with np.errstate(invalid="ignore"):
            keep = (stars >= lv.lowest) & (stars <= lv.highest)
            if not lv.measured:
                keep &= ~(nm > lv.highest)  # nor the map without mods above the level (an unknown one may be)
        if goal == "farm":
            keep &= farmable
        picked = np.flatnonzero(keep)
        if not len(picked):
            continue
        delta = stars[picked] - lv.stars
        if not lv.measured:
            delta = np.fmax(nm[picked] - lv.stars, delta)
        if goal == "farm":
            curves = _curves(pp, table, maps[picked], want, client)
            promise = _pp_at(curves, practice_scale(delta))
        else:
            promise = -np.abs(delta + 0.3)
            if focus:
                cols = configuration_columns(table, maps[picked], hr, hd, want.rate, RELEVANCE_COLUMNS)
                promise = promise + 3 * np.mean([relevance(cols, skill) for skill in focus], axis=0)
        usable = np.isfinite(promise)
        found.append((promise[usable], w, maps[picked][usable]))
    if not found:
        return []
    promise = np.concatenate([p for p, _, _ in found])
    which = np.concatenate([np.full(len(p), w) for p, w, _ in found])
    table_maps = np.concatenate([m for _, _, m in found])
    best = np.argsort(-promise, kind="stable")[:limit]
    rows = []
    for w in sorted(set(which[best].tolist())):
        want = wanted[w]
        chosen = table_maps[best[which[best] == w]]
        index = record_of[chosen]
        records = dict(zip(index.tolist(), pool.iloc[index].to_dict("records"), strict=True))
        made = rows_at(table, records, record_of, chosen, "HR" in want.mods, "HD" in want.mods, want.rate, client)
        for i, row in zip(index.tolist(), made, strict=True):
            record = records[i]
            row.update(
                config=want.config,
                mods=want.mods,
                rate=want.rate,
                client=client,
                status=record.get("status"),
                length_s=row.get("drain_length"),
                stars_nm=record.get("stars"),
                pp_curve=pp.curve(row["md5"], want.mods, client) if pp is not None and _standard(want) else None,
            )
            rows.append(row)
    return rows


def _standard(want: Wanted) -> bool:
    return want.mods in CONFIGS and abs(want.rate - standard_rate(want.mods)) < 1e-6


def _curves(pp: PpTable | None, table: VariantTable, maps: np.ndarray, want: Wanted, client: str) -> np.ndarray:
    """The maps' pp curves in ``want`` (maps, accuracies; NaN where the pp table has none)."""
    out = np.full((len(maps), len(pp.accuracies) if pp else 1), np.nan)
    if pp is None or not _standard(want) or want.mods not in pp.configs or client not in pp.clients:
        return out
    rows = np.array([pp.index.get(table.md5[t], -1) for t in maps], dtype=np.int64)
    known = rows >= 0
    values = pp.pp[rows[known], pp.configs.index(want.mods), pp.clients.index(client)].astype(float)
    out[known] = np.where(values == MISSING, np.nan, values / pp.scale)
    return out


def _pp_at(curves: np.ndarray, accuracy: np.ndarray) -> np.ndarray:
    """The pp of each curve at its accuracy: between the stored points, geometrically (as ``sampled_pp``)."""
    grid = np.asarray(ACCURACIES, dtype=float)
    upper = np.clip(np.searchsorted(grid, accuracy, side="left"), 1, len(grid) - 1)
    lower = upper - 1
    t = (accuracy - grid[lower]) / (grid[upper] - grid[lower])
    rows = np.arange(len(curves))
    with np.errstate(divide="ignore", invalid="ignore"):
        low, high = np.log(curves[rows, lower]), np.log(curves[rows, upper])
        return np.exp(low * (1 - t) + high * t)
