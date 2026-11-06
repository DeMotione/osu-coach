"""The player's comfort level and the weight of each replay by how far its star rating is from it."""

from __future__ import annotations

import datetime as _dt
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from osu_coach.domain.analysis.models import ReplayMeta
from osu_coach.domain.replays.configuration import from_meta

LEVEL_BAND = 0.5  # ★: replays within ± this of the player's level count fully
LEVEL_SIGMA = 0.5  # ★: Gaussian fall-off outside the band
RECENT_DAYS = 30  # the level is measured on the replays of the last 30 days (before the newest one) ...
RECENT_MIN = 15  # ... or on the newest 15 if there are fewer
MIN_WEIGHT = 1e-6


# ------------------------------------------------------------------ difficulty weighting
def replay_weight(stars, level: float, band: float = LEVEL_BAND, sigma: float = LEVEL_SIGMA) -> np.ndarray:
    """Weight of a replay by the distance of its star rating (with mods) from the player's level: 1 within
    ± ``band``, then a Gaussian tail (``sigma``): 1★ off ≈ 0.61, 1.5★ ≈ 0.14, 2★ ≈ 0.01, 3★ ≈ 0.00004.
    Unknown star rating or level = 1."""
    s = np.asarray(stars, dtype=float)
    if level is None or not np.isfinite(level):
        return np.ones_like(s)
    d = np.maximum(np.abs(s - level) - band, 0.0)
    w = np.exp(-0.5 * (np.nan_to_num(d) / sigma) ** 2)
    return np.where(np.isfinite(s), np.maximum(w, MIN_WEIGHT), 1.0)


def _utc(v) -> _dt.datetime | None:
    """A date (ISO 8601 text, a datetime or a date) in UTC; naive ones are UTC. None when it isn't one."""
    if isinstance(v, str):
        try:
            v = _dt.datetime.fromisoformat(v.strip())
        except ValueError:
            return None
    elif isinstance(v, _dt.date) and not isinstance(v, _dt.datetime):
        v = _dt.datetime(v.year, v.month, v.day)
    if not isinstance(v, _dt.datetime):
        return None
    return v.replace(tzinfo=_dt.UTC) if v.tzinfo is None else v.astimezone(_dt.UTC)


def weight_table(level: float, band: float = LEVEL_BAND, sigma: float = LEVEL_SIGMA) -> list[tuple[float, float]]:
    """(★ off the level, weight) pairs for explanations."""
    return [(d, float(replay_weight([level + d], level, band, sigma)[0])) for d in (0.5, 1.0, 1.5, 2.0, 3.0)]


CLEAN_PASS_MISSES_PER_100 = 5.0


def _misses_per_100(m: ReplayMeta) -> float:
    return m.head_misses / max(m.n_objects, 1) * 100


def clean_pass(m: ReplayMeta) -> bool:
    """A finished play with at most 5 misses per 100 notes: getting through a map with many more (lazer lets you)
    is no real pass of it."""
    return bool(m.completed) and _misses_per_100(m) <= CLEAN_PASS_MISSES_PER_100


# ------------------------------------------------------------------ comfort level
COMFORT_MISSES_PER_100 = 2.0  # a "clean" play for the comfort level: finished with at most this many misses / 100
COMFORT_SETUPS = 3  # different clean map/mod setups needed for a measured comfort level
MEASURED, PROVISIONAL, NO_COMFORT = "measured", "provisional", "none"


@dataclass(frozen=True)
class Comfort:
    """The player's comfort level: the one level every page, the replay weights and the ratings use.

    ``status`` says how solid it is: ``measured`` (from ``COMFORT_SETUPS``+ different clean map/mod setups; the
    skill ratings need this), ``provisional`` (fewer: an estimate from what there is) or ``none`` (no play with a
    star rating)."""

    stars: float | None
    status: str
    setups: int  # different clean map/mod setups among the recent plays
    recent_n: int  # recent plays it was measured on
    recent_since: _dt.datetime | None

    @property
    def measured(self) -> float | None:
        """The level when it is measured, else None."""
        return self.stars if self.status == MEASURED else None


def recent_plays(plays: Sequence[ReplayMeta]) -> list[tuple[ReplayMeta, _dt.datetime | None]]:
    """The plays of the last ``RECENT_DAYS`` days before the newest one, or the newest ``RECENT_MIN`` when there are
    fewer (plays without a date only then), newest first, each with its date in UTC."""
    dated = [(m, _utc(m.date)) for m in plays]
    with_date = sorted((x for x in dated if x[1] is not None), key=lambda x: x[1], reverse=True)
    ordered = with_date + [x for x in dated if x[1] is None]
    if not with_date:
        return ordered
    newest = with_date[0][1]
    recent = [x for x in with_date if x[1] >= newest - _dt.timedelta(days=RECENT_DAYS)]
    return recent if len(recent) >= RECENT_MIN else ordered[:RECENT_MIN]


def _setup_key(m: ReplayMeta) -> str:
    """The play's map/mod setup; plays with an unreadable setup (no valid rate) each count as their own."""
    try:
        return from_meta(m.to_dict()).key
    except ValueError:
        return f"{m.beatmap_md5}:{m.key}"


def comfort(plays: Sequence[ReplayMeta] | None) -> Comfort:
    """The comfort level of these plays, from the recent ones (:func:`recent_plays`):

    * measured: the 75th percentile over ``COMFORT_SETUPS``+ different map/mod setups of each setup's median star
      rating, counting only finished plays with at most ``COMFORT_MISSES_PER_100`` misses per 100 notes;
    * provisional, with fewer setups: the 75th percentile of those clean plays, or with none at all the 25th
      percentile of the plays' star ratings minus 0.4."""
    if not plays:
        return Comfort(None, NO_COMFORT, 0, 0, None)
    recent = recent_plays(plays)
    times = [t for _, t in recent if t is not None]
    since = min(times) if times else None
    rated = [m for m, _ in recent if m.stars is not None and math.isfinite(m.stars)]
    if not rated:
        return Comfort(None, NO_COMFORT, 0, len(recent), since)
    clean = [m for m in rated if m.completed and _misses_per_100(m) <= COMFORT_MISSES_PER_100]
    by_setup: dict[str, list[float]] = {}
    for m in clean:
        by_setup.setdefault(_setup_key(m), []).append(m.stars)
    setups = [float(np.median(v)) for v in by_setup.values()]
    if len(setups) >= COMFORT_SETUPS:
        return Comfort(float(np.quantile(setups, 0.75)), MEASURED, len(setups), len(recent), since)
    stars = (
        float(np.quantile([m.stars for m in clean], 0.75))
        if clean
        else float(np.quantile([m.stars for m in rated], 0.25) - 0.4)
    )
    return Comfort(stars, PROVISIONAL, len(setups), len(recent), since)
