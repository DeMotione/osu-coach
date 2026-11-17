"""The pool's maps with mods from a table, instead of from their .osu files.

A modified search asks for every configuration (HR, HD, a rate from 1.10 to 2.00) of every pool map. Worked out
from the .osu files that is hundreds of calculations a map, and the files have to be downloaded first. The
:class:`VariantTable` holds what those calculations give, made once when the pool is built
(``backend/tools/build_variant_table.py``):

- rosu's values of every configuration: stars, aim and speed, and the slider factor and the evenness, which HD
  leaves alone. They are what does not follow from the rate, so the whole grid is stored (rounded, see ``scales``).
- the pattern statistics. Nearly all of them are the previous rate's, scaled by the rate (:func:`rescale`): a
  velocity grows with the rate, a duration shrinks, a share stays. A row is stored for the first rate and for every
  rate at which that stops being true (a stream that only counts as one from some rate on): ``segments``.

A row made from the table (:func:`table_rows`) is the row the .osu file gives, to the rounding of the stored values.
:func:`recommend_from_table` ranks them like ``skillset.recommend_modified`` ranks rows: it scores every
configuration with arrays, hands the few that can be among a goal's best to ``recommend_modified`` as rows, and the
rest as a ``Tally``, so the two cannot drift apart in what they show.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

import numpy as np

from osu_coach.domain.maps.configuration import SearchOptions
from osu_coach.domain.maps.skillset import (
    FEATURE_POINTS,
    GOALS,
    HISTORY_WEIGHT,
    PRECOMPUTED,
    REFERENCE_GRID,
    RISK_WEIGHT,
    SKILL_SCALE,
    SPEED_MIN_TEMPO_RATIO,
    STAR_SCALE,
    STAR_WINDOW,
    Recommendation,
    Tally,
    recommend_modified,
)
from osu_coach.domain.maps.suggestions import SKILLS, skill_scores
from osu_coach.domain.numeric.values import finite_or_none
from osu_coach.domain.player import algorithm as alg
from osu_coach.domain.player.engines.skill_scale import SPEED_POINTS, expected_speed_bpm, speed_bpm_for_rating
from osu_coach.domain.replays.configuration import Configuration
from osu_coach.domain.replays.models import MOD_BITS

RATES = (100, *range(110, 201))  # hundredths: no rate change, then every rate a search can ask for
# What pattern_stats gives as numbers, in the table's column order.
PATTERN_COLUMNS = (
    "cs",
    "ar",
    "od",
    "hp",
    "hit300_ms",
    "hit100_ms",
    "hit50_ms",
    "bpm",
    "drain_length",
    "n_objects",
    "circle_share",
    "slider_share",
    "stream_share",
    "burst_share",
    "jump_share",
    "spaced_share",
    "spaced_stream_share",
    "stream_bpm",
    "burst_bpm",
    "speed_bpm",
    "speed_runs",
    "max_run",
    "run_duration_p90",
    "run_rest_median",
    "long_runs",
    "stream_notes",
    "n_jumps",
    "jump_dist",
    "jump_velocity",
    "flow_velocity",
    "flow_turn_share",
    "sharp_share",
    "slider_velocity",
    "slider_length_norm",
    "slider_turn",
    "slider_transition",
    "reverse_share",
    "density_p90",
    "density_median",
    "odd_rhythm_share",
    "q_top_left",
    "q_top_right",
    "q_bottom_left",
    "q_bottom_right",
)
# How a pattern statistic follows the rate while the patterns themselves stay the same.
RATE_UP = frozenset(
    {"bpm", "stream_bpm", "burst_bpm", "speed_bpm", "jump_velocity", "flow_velocity", "slider_velocity"}
)
RATE_DOWN = frozenset(
    {
        "drain_length",
        "hit300_ms",
        "hit100_ms",
        "hit50_ms",
        "run_duration_p90",
        "run_rest_median",
        "slider_transition",
    }
)
COUNTS = ("n_objects", "speed_runs", "max_run", "long_runs", "stream_notes", "n_jumps")  # whole numbers in a row
TEXTS = ("md5", "title", "artist", "version", "creator")
BY_CONFIGURATION = ("stars", "aim", "speed")  # (maps, HR, HD, rates)
BY_GEOMETRY = ("slider_factor", "evenness")  # (maps, HR, rates): HD leaves them alone
SCALES = {"stars": 1000.0, "aim": 200.0, "speed": 200.0, "slider_factor": 2000.0, "evenness": 2000.0}
MISSING = 65535  # no value (a stored value is a uint16)
SAME = 1e-6  # a pattern statistic is "the previous rate's, scaled" within this (relative and absolute)
TIE = 1e-9  # scores this close are left to recommend_modified to order
BLOCK = 4096  # maps whose stars are read at a time
CHUNK = 100_000  # configurations scored at a time
_MODS = (("HD", MOD_BITS["HD"]), ("HR", MOD_BITS["HR"]), ("DT", MOD_BITS["DT"]))
_REASONS = (
    "Target demand or relevance unknown",
    "Insufficient target relevance",
    "Assessed map demand unknown",
    "Tapping tempo too far below target",
)
_OUTSIDE = -1  # reason code: not in the goal's star window


@dataclass(frozen=True, eq=False)
class VariantTable:
    """What the configurations of the pool's maps have beyond the maps' own rows (see the module)."""

    md5: tuple[str, ...]
    found: np.ndarray  # bool (maps): the map's .osu file was there when the table was made
    stars: np.ndarray  # uint16 (maps, HR, HD, rates): value * scale, MISSING for none
    aim: np.ndarray
    speed: np.ndarray
    slider_factor: np.ndarray  # uint16 (maps, HR, rates)
    evenness: np.ndarray
    segment_keys: np.ndarray  # int64, rising: (map * 2 + HR) * 128 + the first rate the row holds for
    segment_rows: np.ndarray  # float32 (segments, columns): the pattern statistics at that rate
    columns: tuple[str, ...] = PATTERN_COLUMNS
    scales: Mapping[str, float] = field(default_factory=lambda: dict(SCALES))

    @cached_property
    def index(self) -> dict[str, int]:
        return {md5: i for i, md5 in enumerate(self.md5)}

    def value(self, name: str, maps, hr, hd, rate) -> np.ndarray:
        """rosu's ``name`` of the configurations (arrays of one shape), NaN for none."""
        stored = getattr(self, name)
        raw = np.asarray(stored[maps, hr, hd, rate] if name in BY_CONFIGURATION else stored[maps, hr, rate])
        return np.where(raw == MISSING, np.nan, raw / self.scales[name])


# ------------------------------------------------------------------ the pattern statistics at another rate
def _preempt(ar: np.ndarray) -> np.ndarray:
    return np.where(ar > 5, 1200 - 150 * (ar - 5), 1200 + 120 * (5 - ar))


def _approach_rate(preempt: np.ndarray) -> np.ndarray:
    return np.where(preempt < 1200, 5 + (1200 - preempt) / 150, 5 - (preempt - 1200) / 120)


def rescale(column: str, values: np.ndarray, old: np.ndarray | float, new: np.ndarray | float) -> np.ndarray:
    """A pattern statistic at the rate ``new``, from its value at the rate ``old`` of the same patterns."""
    if column in RATE_UP:
        return values * new / old
    if column in RATE_DOWN:
        return values * old / new
    if column == "ar":  # the time a note is visible shrinks with the rate
        return _approach_rate(_preempt(values) * old / new)
    if column == "od":  # and so does the 300 window
        return (79.5 - (79.5 - 6 * values) * old / new) / 6
    return values


def segment_starts(rows: np.ndarray, columns: Sequence[str] = PATTERN_COLUMNS) -> list[int]:
    """Where a map's pattern statistics have to be stored: ``rows`` are the exact ones at every rate of
    :data:`RATES` (rates, columns); the result the rates (indices) whose row is not the stored one before it,
    scaled. Every other rate's row is, within :data:`SAME`, which is what :func:`pattern_columns` relies on."""
    starts = [0]
    base = rows[0].astype(np.float32).astype(np.float64)
    for i in range(1, len(rows)):
        old, new = RATES[starts[-1]] / 100, RATES[i] / 100
        predicted = np.array([rescale(c, base[j], old, new) for j, c in enumerate(columns)], dtype=np.float64)
        if not np.isclose(predicted, rows[i], rtol=SAME, atol=SAME, equal_nan=True).all():
            starts.append(i)
            base = rows[i].astype(np.float32).astype(np.float64)
    return starts


def pattern_columns(table: VariantTable, maps, hr, rate, columns: Sequence[str]) -> dict[str, np.ndarray]:
    """The pattern statistics ``columns`` of configurations (arrays of the table's map, HR and rate indices)."""
    keys = (np.asarray(maps, dtype=np.int64) * 2 + hr) * 128 + rate
    segment = np.searchsorted(table.segment_keys, keys, side="right") - 1
    rates = np.asarray(RATES, dtype=np.float64) / 100
    old = rates[table.segment_keys[segment] % 128]
    new = rates[rate]
    rows = np.asarray(table.segment_rows[segment])

    def values(column: str) -> np.ndarray:
        return rows[:, table.columns.index(column)].astype(np.float64)

    return {column: rescale(column, values(column), old, new) for column in columns}


# ------------------------------------------------------------------ skillset's composites and relevance, on columns
def _get(cols: Mapping[str, np.ndarray], key: str, default: float = 0.0):
    values = cols.get(key)
    return default if values is None else np.where(np.isfinite(values), values, default)


def _finite(cols: Mapping[str, np.ndarray], key: str):
    values = cols.get(key)
    return False if values is None else np.isfinite(values)


def composites(cols: Mapping[str, np.ndarray], hd, skills: Sequence[str], n: int) -> dict[str, np.ndarray]:
    """``skillset._features`` on columns: the composite of each of ``skills`` for ``n`` rows (NaN: none).
    ``hd``: whether a row is played with HD. The formulas are skillset's, term for term; the tests hold them equal."""
    radius = np.maximum(1.0, 54.4 - 4.48 * _get(cols, "cs", 4))
    bpm = np.maximum(_get(cols, "stream_bpm"), _get(cols, "burst_bpm"))
    has_bpm = _finite(cols, "stream_bpm") | _finite(cols, "burst_bpm")
    out = {}
    with np.errstate(all="ignore"):
        for skill in skills:
            if skill == "aim":
                value = _get(cols, "jump_velocity") * 1000 / (2 * radius) * (1 + 0.3 * _get(cols, "sharp_share"))
                known = _finite(cols, "cs") & _finite(cols, "jump_velocity") & _finite(cols, "sharp_share")
            elif skill == "flow_aim":
                value = (
                    np.where(
                        _finite(cols, "flow_velocity"),
                        _get(cols, "flow_velocity") * 1000 / (2 * radius),
                        _get(cols, "aim") * bpm / 180,
                    )
                    * np.sqrt(np.maximum(0, _get(cols, "spaced_stream_share")))
                    * (1 + 0.3 * _get(cols, "flow_turn_share"))
                )
                known = _finite(cols, "aim") & _finite(cols, "spaced_stream_share") & has_bpm
            elif skill == "speed":
                value = (
                    np.where(_get(cols, "speed_runs") >= 3, _get(cols, "speed_bpm"), 0.0)
                    if "speed_runs" in cols
                    else bpm
                )
                known = True
            elif skill == "stamina":
                value = (
                    bpm
                    * np.log1p(np.maximum(0, _get(cols, "stream_notes")))
                    / math.log(401)
                    * np.sqrt(np.maximum(0, _get(cols, "max_run")) / 32)
                    * (np.maximum(0, _get(cols, "drain_length")) / 120) ** 0.15
                    * (np.maximum(0.1, _get(cols, "run_duration_p90", 10)) / 10) ** 0.25
                    * (1 + 0.15 / (1 + np.maximum(0, _get(cols, "run_rest_median", 2))))
                )
                known = _finite(cols, "stream_notes") & _finite(cols, "max_run") & _finite(cols, "drain_length")
                known = known & has_bpm
            elif skill == "accuracy":
                od = _get(cols, "od", 8)
                value = (
                    20
                    * (
                        0.7 / np.maximum(1, _get(cols, "hit300_ms", 80 - 6 * od))
                        + 0.4 / np.maximum(1, _get(cols, "hit100_ms", 140 - 8 * od))
                        + 0.3 / np.maximum(1, _get(cols, "hit50_ms", 200 - 10 * od))
                    )
                    * (1 + 2 * _get(cols, "odd_rhythm_share"))
                    * (1 + 0.03 * _get(cols, "density_p90"))
                )
                known = _finite(cols, "od") & _finite(cols, "odd_rhythm_share") & _finite(cols, "density_p90")
            elif skill == "sliders":
                value = (
                    _get(cols, "slider_velocity")
                    * 1000
                    / (2 * radius)
                    * (1 + _get(cols, "reverse_share"))
                    * (1 + 10 * np.maximum(0, 1 - _get(cols, "slider_factor", 1)))
                    * (1 + 0.02 * _get(cols, "slider_length_norm") + 0.03 * _get(cols, "slider_turn"))
                    * (1 + 0.1 / np.maximum(0.1, _get(cols, "slider_transition", 1000) / 1000))
                )
                known = _finite(cols, "cs") & _finite(cols, "slider_velocity") & _finite(cols, "reverse_share")
                known = known & _finite(cols, "slider_factor")
            elif skill == "reading":
                density, ar = _get(cols, "density_p90"), _get(cols, "ar", 9)
                value = (
                    density * (1 + _get(cols, "odd_rhythm_share"))
                    + alg.READ_LOW_WEIGHT * np.maximum(0, alg.READ_LOW_AR - ar) ** 2
                    + alg.READ_FAST_WEIGHT * np.maximum(0, ar - alg.READ_FAST_AR) ** 2
                    + np.where(hd, 1, 0)
                    * (
                        alg.READ_HD_BASE
                        + alg.READ_HD_LOW_WEIGHT * np.maximum(0, alg.READ_LOW_AR - ar) ** 2
                        + alg.READ_HD_HIGH_WEIGHT * np.maximum(0, ar - alg.READ_HD_UPPER_AR) ** 2
                    )
                    * (1 + alg.READ_HD_DENSITY_WEIGHT * density)
                )
                known = _finite(cols, "density_p90") & _finite(cols, "odd_rhythm_share") & _finite(cols, "ar")
            else:  # consistency
                value = np.sqrt(np.maximum(0, _get(cols, "drain_length")) / 120) * (
                    0.5 + 0.5 * np.clip(_get(cols, "evenness", 1), 0, 1)
                )
                known = _finite(cols, "drain_length") & _finite(cols, "evenness")
            value = np.broadcast_to(np.asarray(value, dtype=np.float64), (n,))
            out[skill] = np.where(known & np.isfinite(value) & (value > 0), value, np.nan)
    return out


def pool_features(cols: Mapping[str, np.ndarray], n: int) -> dict[str, np.ndarray]:
    """The composites of ``n`` pool maps (no mods), as the columns ``skillset._features`` reads instead of computing
    them for every recommendation (NaN: none)."""
    return {PRECOMPUTED + skill: values for skill, values in composites(cols, False, tuple(SKILLS), n).items()}


def _c(values, low: float, high: float):
    if values is None:
        return 0.0
    values = np.asarray(values, dtype=np.float64)
    return np.where(np.isfinite(values), np.clip((values - low) / (high - low), 0, 1), 0.0)


def relevance(cols: Mapping[str, np.ndarray], skill: str) -> np.ndarray:
    """``suggestions.skill_scores`` on columns, for one skill."""
    g = cols.get

    def aim_ratio():
        aim, speed = np.asarray(_get(cols, "aim"), dtype=np.float64), np.asarray(_get(cols, "speed"), dtype=np.float64)
        with np.errstate(all="ignore"):
            return np.where(aim + speed > 0, aim / (aim + speed), 0.5)

    def jumpy():
        return _get(cols, "jump_share") + 0.5 * _get(cols, "spaced_share")

    if skill == "aim":
        return 0.6 * _c(jumpy(), 0.05, 0.40) + 0.4 * _c(aim_ratio(), 0.45, 0.60)
    if skill == "flow_aim":
        return _c(g("spaced_stream_share"), 0.02, 0.20) + 0.0
    if skill == "speed":
        tappy = _get(cols, "stream_share") + 0.6 * _get(cols, "burst_share")
        return 0.7 * _c(tappy, 0.05, 0.40) + 0.3 * _c(1 - aim_ratio(), 0.40, 0.55)
    if skill == "stamina":
        return (
            0.5 * _c(g("stream_notes"), 50, 400) + 0.3 * _c(g("max_run"), 12, 48) + 0.2 * _c(g("drain_length"), 90, 300)
        )
    if skill == "accuracy":
        return 0.5 * _c(g("od"), 6.5, 9.5) + 0.3 * _c(g("circle_share"), 0.3, 0.8) + 0.2 * (1 - _c(jumpy(), 0.1, 0.5))
    if skill == "sliders":
        return (
            0.45 * _c(g("slider_share"), 0.25, 0.65)
            + 0.35 * _c(1 - _get(cols, "slider_factor", 1.0), 0, 0.08)
            + 0.2 * _c(g("reverse_share"), 0.05, 0.35)
        )
    if skill == "reading":
        return 0.6 * _c(g("density_p90"), 4, 10) + 0.4 * _c(g("odd_rhythm_share"), 0.0, 0.15)
    return 0.5 * _c(g("drain_length"), 90, 270) + 0.5 * _c(g("evenness"), 0.3, 0.7)


# what the composites and the relevance read
_NEEDS = {
    "aim": ("cs", "jump_velocity", "sharp_share", "jump_share", "spaced_share", "aim", "speed"),
    "flow_aim": ("cs", "flow_velocity", "aim", "stream_bpm", "burst_bpm", "spaced_stream_share", "flow_turn_share"),
    "speed": ("speed_bpm", "speed_runs", "stream_share", "burst_share", "aim", "speed"),
    "stamina": (
        "stream_bpm",
        "burst_bpm",
        "stream_notes",
        "max_run",
        "drain_length",
        "run_duration_p90",
        "run_rest_median",
    ),
    "accuracy": (
        "od",
        "hit300_ms",
        "hit100_ms",
        "hit50_ms",
        "odd_rhythm_share",
        "density_p90",
        "circle_share",
        "jump_share",
        "spaced_share",
    ),
    "sliders": (
        "cs",
        "slider_velocity",
        "reverse_share",
        "slider_factor",
        "slider_length_norm",
        "slider_turn",
        "slider_transition",
        "slider_share",
    ),
    "reading": ("density_p90", "odd_rhythm_share", "ar"),
    "consistency": ("drain_length", "evenness"),
}


def reference_curves(pool: Mapping[str, np.ndarray], assessed: Sequence[str]) -> dict[str, list[float | None]]:
    """``skillset.reference_curves`` from the pool's columns (arrays by name)."""
    stars = np.asarray(pool["stars"], dtype=np.float64)
    rated = np.isfinite(stars) & (stars > 0)
    keys = [key for key in assessed if key != "speed"]
    features = composites(pool, False, keys, len(stars))
    curves: dict[str, list[float | None]] = {}
    for key in keys:
        known = rated & np.isfinite(features[key])
        values, near_stars = features[key][known], stars[known]
        curve: list[float | None] = []
        for point in REFERENCE_GRID:
            near = values[np.abs(near_stars - point) <= 0.5]
            curve.append(float(np.median(near)) if len(near) >= 10 else None)
        curves[key] = curve
    return curves


def _reference(curve: Sequence[float | None], stars: np.ndarray) -> np.ndarray:
    """``recommend_modified``'s reference of a skill at star ratings: the curve's point at or above the star
    rating, and between the known points around it only where that one is unknown (NaN: no point is known)."""
    grid = np.asarray(REFERENCE_GRID)
    values = np.array([np.nan if value is None else value for value in curve], dtype=np.float64)
    n = len(grid)
    known = np.flatnonzero(np.isfinite(values))
    if not len(known):
        return np.full(stars.shape, np.nan)
    at = np.arange(n)
    below = np.searchsorted(known, at, side="right") - 1  # the last known point at or below each point
    above = np.searchsorted(known, at, side="left")  # the first known point at or above it
    before = np.where(below >= 0, known[np.maximum(below, 0)], -1)
    after = np.where(above < len(known), known[np.minimum(above, len(known) - 1)], -1)
    pos = np.searchsorted(grid, stars, side="left")
    b = before[np.minimum(pos, n - 1)]
    a = np.where(pos < n, after[np.minimum(pos, n - 1)], -1)
    low, high = values[np.maximum(b, 0)], values[np.maximum(a, 0)]
    with np.errstate(all="ignore"):
        between = low + (high - low) * (stars - grid[np.maximum(b, 0)]) / (
            grid[np.maximum(a, 0)] - grid[np.maximum(b, 0)]
        )
    return np.where((b >= 0) & (a >= 0) & (b != a), between, np.where(b >= 0, low, high))


# ------------------------------------------------------------------ the search grid
@dataclass(frozen=True)
class _Grid:
    """The configurations a search asks for, as indices into the table (one entry a configuration)."""

    hr: np.ndarray
    hd: np.ndarray
    rate: np.ndarray  # index into RATES
    mods: tuple[int, ...]
    order: np.ndarray  # where a configuration's id sorts among a map's (recommend_modified breaks ties by id)

    def __len__(self) -> int:
        return len(self.mods)


def _grid(options: SearchOptions, client: str) -> _Grid:
    configs = options.configurations("", client)
    try:
        rate = [RATES.index(round(c.rate * 100)) for c in configs]
    except ValueError as exc:
        raise ValueError("The variant table has no such rate.") from exc
    order = np.empty(len(configs), dtype=np.int64)
    order[np.argsort(np.array([c.key for c in configs]), kind="stable")] = np.arange(len(configs))
    return _Grid(
        np.array([int(c.hr) for c in configs]),
        np.array([int(c.hd) for c in configs]),
        np.array(rate),
        tuple(c.mods for c in configs),
        order,
    )


def _mods_text(mods: int) -> str:
    return "".join(name for name, bit in _MODS if mods & bit) or "NM"


def _clean(value: float) -> float | None:
    return float(value) if math.isfinite(value) else None


def _rows(
    table: VariantTable, records: Sequence[Mapping[str, Any]], grid: _Grid, client: str, maps, record_of, configs
) -> Iterator[dict]:
    """The rows of configurations: ``maps`` (table indices) and ``configs`` (grid indices), one a row, with the
    pool record of each map (``record_of``: table index -> record index)."""
    maps, configs = np.asarray(maps, dtype=np.int64), np.asarray(configs, dtype=np.int64)
    if not len(maps):
        return
    hr, hd, rate = grid.hr[configs], grid.hd[configs], grid.rate[configs]
    pattern = pattern_columns(table, maps, hr, rate, table.columns)
    rosu = {name: table.value(name, maps, hr, hd, rate) for name in (*BY_CONFIGURATION, *BY_GEOMETRY)}
    for i in range(len(maps)):
        record = records[record_of[maps[i]]]
        mods = grid.mods[configs[i]]
        rate_value = RATES[rate[i]] / 100
        row: dict[str, Any] = {key: record.get(key) for key in TEXTS}
        for key in ("beatmap_id", "beatmapset_id"):
            number = finite_or_none(record.get(key))
            row[key] = int(number) if number is not None and number > 0 else 0
        for column, values in pattern.items():
            row[column] = _clean(values[i])
        for column in COUNTS:
            if row.get(column) is not None:
                row[column] = int(round(row[column]))
        for name, values in rosu.items():
            row[name] = _clean(values[i])
        row["max_combo"] = finite_or_none(record.get("max_combo"))
        if not mods and rate_value == 1.0:
            row["stars_dt"] = finite_or_none(record.get("stars_dt"))
        row.update(skill_scores(row))
        row["configuration_id"] = Configuration(str(record.get("md5")), mods, rate_value, client).key
        row["mods"] = _mods_text(mods)
        row["rate"] = rate_value
        yield row


def _in_pool(table: VariantTable, records: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    """The table's maps that are pool records: their table indices, and table index -> record index (-1: none)."""
    record_of = np.full(len(table.md5), -1, dtype=np.int64)
    index = table.index
    for i, record in enumerate(records):
        t = index.get(str(record.get("md5") or ""))
        if t is not None and table.found[t] and record_of[t] < 0:
            record_of[t] = i
    return np.flatnonzero(record_of >= 0), record_of


def table_rows(
    table: VariantTable, records: Sequence[Mapping[str, Any]], options: SearchOptions, client: str
) -> Iterator[dict]:
    """Every available configuration of the pool's maps as a row, in pool order: what ``variant_rows`` gives from
    the .osu files, without them."""
    grid = _grid(options, client)
    maps, record_of = _in_pool(table, records)
    maps = maps[np.argsort(record_of[maps], kind="stable")]
    for start in range(0, len(maps), 256):
        part = maps[start : start + 256]
        stars = np.asarray(table.stars[part])[:, grid.hr, grid.hd, grid.rate]
        m, c = np.nonzero((stars != MISSING) & (stars > 0))
        yield from _rows(table, records, grid, client, part[m], record_of, c)


# ------------------------------------------------------------------ the search
@dataclass(frozen=True, slots=True)
class TableSearch:
    """What :func:`recommend_from_table` found, and how much of the pool the table covers."""

    recommendation: Recommendation
    maps: int  # pool maps the table has
    missing_maps: int  # pool maps it does not have
    unusable_maps: int  # maps none of whose configurations has statistics
    unavailable_configurations: int


def _history(table: VariantTable, grid: _Grid, client: str, history: Mapping[str, float]):
    """The replay history of table configurations: (map * configurations + configuration, rising) and the values."""
    where = {(mods, RATES[rate]): i for i, (mods, rate) in enumerate(zip(grid.mods, grid.rate.tolist()))}
    found = {}
    for key, value in history.items():
        try:
            md5, mods, rate, key_client, lazer_mods = json.loads(key)
            hundredths = round(float(rate) * 100)
            t = table.index.get(md5)
            config = where.get((mods, hundredths))
        except (TypeError, ValueError):
            continue
        if t is None or config is None or key_client != client or lazer_mods != "[]":
            continue
        if Configuration(md5, mods, hundredths / 100, client).key == key:
            found[t * len(grid) + config] = float(value)
    keys = np.array(sorted(found), dtype=np.int64)
    return keys, np.array([found[k] for k in keys.tolist()], dtype=np.float64)


def recommend_from_table(
    table: VariantTable,
    records: Sequence[Mapping[str, Any]],  # the pool's map rows
    pool: Mapping[str, np.ndarray],  # and its columns, for the reference curves
    options: SearchOptions,
    client: str,
    theta: float,
    abilities: dict[str, float],
    skill: str,
    assessed: tuple[str, ...],
    kappa: float,
    min_relevance: float,
    played: frozenset[str],
    history: dict[str, float],
    limit: int = 100,
) -> TableSearch:
    """``recommend_modified`` over every configuration ``options`` asks for of every pool map the table has."""
    grid = _grid(options, client)
    maps, record_of = _in_pool(table, records)
    n = len(maps)
    keys = [key for key in assessed if key != "speed"]
    rated = all(key in abilities for key in assessed)
    references = reference_curves(pool, keys) if rated else {}

    def ranked(rows) -> Recommendation:
        return recommend_modified(
            records, rows, theta, abilities, skill, assessed, kappa, min_relevance, played, history, limit, references
        )

    empty = ranked(())  # the inputs are checked, and the goals known
    if not rated:  # nothing is looked up for a skill without a rating, as in the search of the files
        return TableSearch(empty, 0, 0, 0, 0)
    goals = list(GOALS)
    targets = [empty.goals[goal].target_stars for goal in goals]
    wanted = [empty.goals[goal].target_demand for goal in goals]
    margins = [GOALS[goal][2] for goal in goals]
    tempo = [speed_bpm_for_rating(w, theta) if skill == "speed" else None for w in wanted]
    was_played = np.array([str(records[record_of[t]].get("md5")) in played for t in maps.tolist()], dtype=bool)
    history_keys, history_values = _history(table, grid, client, history)
    needs = tuple(dict.fromkeys(column for key in assessed for column in _NEEDS[key]))
    others = [key for key in assessed if key != skill]
    scale = table.scales["stars"]

    def evaluate(m: np.ndarray, c: np.ndarray, stars: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Each goal's verdict on configurations of maps that were not played (``m``: index into ``maps``, ``c``:
        into the grid, ``stars``: theirs): the reason code (0: it can be ranked) and F (-inf unless ranked), both
        (goals, configurations)."""
        t, hr, hd, rate = maps[m], grid.hr[c], grid.hd[c], grid.rate[c]
        cols = pattern_columns(table, t, hr, rate, [column for column in needs if column in table.columns])
        for name in ("aim", "speed", "slider_factor", "evenness"):
            if name in needs:
                cols[name] = table.value(name, t, hr, hd, rate)
        features = composites(cols, hd.astype(bool), assessed, len(m))
        demands = {}
        with np.errstate(all="ignore"):
            for key in assessed:
                if key == "speed":
                    tempo_ratio = features[key] / expected_speed_bpm(theta)
                    demands[key] = np.clip(50 + SPEED_POINTS * np.log2(tempo_ratio), 0, 100)
                else:
                    reference = _reference(references[key], stars)
                    reference = np.where(reference > 0, reference, np.nan)
                    demands[key] = 50 + 20 * (stars - theta) + FEATURE_POINTS[key] * np.log2(features[key] / reference)
        share = np.broadcast_to(np.asarray(relevance(cols, skill), dtype=np.float64), (len(m),))
        told = np.zeros(len(m))
        if len(history_keys):
            flat = t * len(grid) + c
            at = np.minimum(np.searchsorted(history_keys, flat), len(history_keys) - 1)
            told = np.where(history_keys[at] == flat, HISTORY_WEIGHT * (history_values[at] - 1), 0.0)
        unknown = ~(np.isfinite(share) & (share >= 0) & (share <= 1)) | ~np.isfinite(demands[skill])
        partly = np.zeros(len(m), dtype=bool)
        for key in others:
            partly |= ~np.isfinite(demands[key])
        speed_bpm = np.where(np.isfinite(features["speed"]), features["speed"], 0.0) if skill == "speed" else None
        reasons = np.full((len(goals), len(m)), _OUTSIDE, dtype=np.int8)
        scores = np.full((len(goals), len(m)), -np.inf)
        for g in range(len(goals)):
            inside = np.abs(stars - targets[g]) <= STAR_WINDOW + 1e-12
            slow = speed_bpm < SPEED_MIN_TEMPO_RATIO * tempo[g] if speed_bpm is not None else False
            reason = np.select([unknown, share < min_relevance, partly, slow], [1, 2, 3, 4], 0)
            reasons[g] = np.where(inside, reason, _OUTSIDE)
            with np.errstate(all="ignore"):
                risk = np.zeros(len(m))
                for key in others:
                    risk = risk + (np.maximum(0.0, demands[key] - (abilities[key] + margins[g])) / 20.0) ** 2
                score = -(((stars - targets[g]) / STAR_SCALE) ** 2) + -(
                    ((demands[skill] - wanted[g]) / SKILL_SCALE) ** 2
                )
                score = score + -RISK_WEIGHT * risk + told
            scores[g] = np.where(reasons[g] == 0, score, -np.inf)
        return reasons, scores

    # every configuration gets each goal's verdict; the ones a goal can rank are kept
    counts: list[dict[str, int]] = [{"Already played": 0, "Outside star window": 0} for _ in goals]
    kept: list[list[tuple[np.ndarray, np.ndarray, np.ndarray]]] = [[] for _ in goals]
    configurations = unusable = 0
    for start in range(0, n, BLOCK):
        stored = np.asarray(table.stars[maps[start : start + BLOCK]])[:, grid.hr, grid.hd, grid.rate]
        available = (stored != MISSING) & (stored > 0)
        configurations += int(available.sum())
        unusable += int((~available.any(axis=1)).sum())
        seen = was_played[start : start + BLOCK]
        active = available & ~seen[:, None]
        stars = stored / scale
        inside_any = np.zeros(stored.shape, dtype=bool)
        for g in range(len(goals)):
            inside = active & (np.abs(stars - targets[g]) <= STAR_WINDOW + 1e-12)
            counts[g]["Already played"] += int(available[seen].sum())
            counts[g]["Outside star window"] += int((active & ~inside).sum())
            inside_any |= inside
        m_all, c_all = np.nonzero(inside_any)
        for at in range(0, len(m_all), CHUNK):
            m, c = m_all[at : at + CHUNK], c_all[at : at + CHUNK]
            reasons, scores = evaluate(m + start, c, stars[m, c])
            for g in range(len(goals)):
                for code, text in enumerate(_REASONS, start=1):
                    number = int((reasons[g] == code).sum())
                    if number:
                        counts[g][text] = counts[g].get(text, 0) + number
                ok = reasons[g] == 0
                kept[g].append((m[ok] + start, c[ok], scores[g][ok]))
    covered = (n, len(records) - n, unusable, n * len(grid) - configurations)
    if not configurations:
        return TableSearch(empty, *covered)

    # a map's best configuration for each goal (the ties are recommend_modified's to order: by configuration id)
    present = np.zeros((len(goals), n), dtype=bool)
    best_score = np.full((len(goals), n), -np.inf)
    best_config = np.zeros((len(goals), n), dtype=np.int64)
    rankable = []
    for g in range(len(goals)):
        m = np.concatenate([part[0] for part in kept[g]]) if kept[g] else np.zeros(0, dtype=np.int64)
        c = np.concatenate([part[1] for part in kept[g]]) if kept[g] else np.zeros(0, dtype=np.int64)
        score = np.concatenate([part[2] for part in kept[g]]) if kept[g] else np.zeros(0)
        order = np.lexsort((grid.order[c], -score, m))
        m, c, score = m[order], c[order], score[order]
        first = np.ones(len(m), dtype=bool)
        first[1:] = m[1:] != m[:-1]
        present[g, m[first]] = True
        best_score[g, m[first]] = score[first]
        best_config[g, m[first]] = c[first]
        rankable.append((m, c, score))

    # recommend_modified's choice of one goal a map, on every map
    hundredths = np.asarray(RATES)[grid.rate][best_config]
    warm, comfort, push = (present[goals.index(goal)] for goal in ("Warm-up", "Comfort", "Push"))
    rate_of = {goal: hundredths[goals.index(goal)] for goal in goals}

    def gap(first: str, second: str) -> np.ndarray:
        return np.abs(rate_of[first] - rate_of[second])

    dropped = {
        "Warm-up": (warm & comfort & push)
        | (warm & comfort & ~push & (gap("Warm-up", "Comfort") <= 15))
        | (warm & push & ~comfort & (gap("Warm-up", "Push") <= 15)),
        "Comfort": comfort & push & (gap("Comfort", "Push") >= 15),
        "Push": comfort & push & (gap("Comfort", "Push") < 15),
    }
    final = np.array([present[g] & ~dropped[goal] for g, goal in enumerate(goals)])

    # the maps that can be among a goal's first `limit`, with every goal's best configurations of theirs
    md5_order = np.empty(n, dtype=np.int64)
    md5_order[np.argsort(np.array([table.md5[t] for t in maps.tolist()]), kind="stable")] = np.arange(n)
    shown = np.zeros(n, dtype=bool)
    for g in range(len(goals)):
        candidates = np.flatnonzero(final[g])
        score = best_score[g, candidates]
        order = np.lexsort((grid.order[best_config[g, candidates]], md5_order[candidates], -score))
        candidates, score = candidates[order], score[order]
        if len(candidates) > limit:
            candidates = candidates[score >= score[limit - 1] - TIE]
        shown[candidates] = True
    handed = set()
    for g, (m, c, score) in enumerate(rankable):
        near = shown[m] & (score >= best_score[g, m] - TIE)
        handed.update(zip(m[near].tolist(), c[near].tolist()))
    handed_m = np.array([m for m, _ in sorted(handed)], dtype=np.int64)
    handed_c = np.array([c for _, c in sorted(handed)], dtype=np.int64)

    # everything else is counted: recommend_modified gives its own verdicts on the rows it gets
    if len(handed_m):
        hr, hd, rate = grid.hr[handed_c], grid.hd[handed_c], grid.rate[handed_c]
        reasons, _ = evaluate(handed_m, handed_c, np.asarray(table.stars[maps[handed_m], hr, hd, rate]) / scale)
        for g in range(len(goals)):
            counts[g]["Outside star window"] -= int((reasons[g] == _OUTSIDE).sum())
            for code, text in enumerate(_REASONS, start=1):
                number = int((reasons[g] == code).sum())
                if number:
                    counts[g][text] -= number
    for g in range(len(goals)):
        moved = int((present[g] & ~final[g] & ~shown).sum())
        if moved:
            counts[g]["Shown in another stage"] = moved
    tally = Tally(
        configurations=configurations - len(handed_m),
        excluded={
            goal: {reason: number for reason, number in counts[g].items() if number} for g, goal in enumerate(goals)
        },
        eligible={goal: int((final[g] & ~shown).sum()) for g, goal in enumerate(goals)},
    )
    order = np.argsort(record_of[maps[handed_m]], kind="stable") if len(handed_m) else handed_m
    rows = list(_rows(table, records, grid, client, maps[handed_m[order]], record_of, handed_c[order]))
    return TableSearch(ranked([*rows, tally]), *covered)
