"""All plays' item groups added up into one table (spec §6.3), with each play weighted.

* recency: a play counts fully up to 180 days older than the newest one, then half as much every 90 days;
* retries: one map/mod setup counts at most as much as 3 plays of it, one mapset at most as much as 5 (the map's
  MD5 when the set is unknown): a play weighs ``min(1, 3 / N_setup, 5 / N_set)`` — against farming one map (fix 3);
* sessions: a play started 40 min or more into a session (plays less than 20 min apart) is flagged ``late``;
* plays whose re-simulation disagrees with the replay (stable: under 97% of the judgements; lazer: counts that don't
  match) are left out.
"""

from __future__ import annotations

import datetime as dt
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from osu_coach.domain.analysis.models import ReplayMeta
from osu_coach.domain.player.engines.irt import constants as K
from osu_coach.domain.player.engines.irt.items import B_COLUMNS, IrtGroups, group
from osu_coach.domain.replays.configuration import from_meta

RECENT_DAYS, HALF_LIFE_DAYS = 180.0, 90.0
SETUP_PLAYS, SET_PLAYS = 3.0, 5.0
SESSION_GAP, LATE_AFTER = dt.timedelta(minutes=20), dt.timedelta(minutes=40)
MIN_AGREEMENT = 0.97


@dataclass(frozen=True, slots=True)
class Merged:
    """The weighted groups of all used plays; ``plays[k]``: the weighted number of plays with items of skill k
    (``acc`` included); ``used`` / ``left_out``: how many plays were used and excluded."""

    groups: IrtGroups
    plays: dict[str, float] = field(default_factory=dict)
    used: int = 0
    left_out: int = 0


def usable(meta: ReplayMeta) -> bool:
    """Whether the play's re-simulation is trusted."""
    if meta.client == "lazer":
        return meta.sim_match is not False
    agreement = meta.sim_agreement
    return not (isinstance(agreement, float) and math.isfinite(agreement) and agreement < MIN_AGREEMENT)


def _setup(meta: ReplayMeta) -> str:
    try:
        return from_meta(meta.to_dict()).key
    except Exception:  # noqa: BLE001 - an odd meta must not stop the merge
        return f"{meta.beatmap_md5}:{meta.mods}@{meta.rate}"


def weights(replays: Sequence[ReplayMeta]) -> np.ndarray:
    """Every play's weight: recency × the setup and mapset caps."""
    dates = [m.date for m in replays]
    known = [d for d in dates if d is not None]
    newest = max(known) if known else None
    setups = [_setup(m) for m in replays]
    sets = [str(m.beatmapset_id) if m.beatmapset_id else str(m.beatmap_md5) for m in replays]
    n_setup, n_set = Counter(setups), Counter(sets)
    out = []
    for d, s, ms in zip(dates, setups, sets, strict=True):
        age = (newest - d).total_seconds() / 86400 if newest is not None and d is not None else 0.0
        recency = 1.0 if age <= RECENT_DAYS else 0.5 ** ((age - RECENT_DAYS) / HALF_LIFE_DAYS)
        out.append(recency * min(1.0, SETUP_PLAYS / n_setup[s], SET_PLAYS / n_set[ms]))
    return np.asarray(out, dtype=float)


def started(meta: ReplayMeta) -> dt.datetime | None:
    """When the play started: a replay's time is when it was saved, at its end."""
    if meta.date is None:
        return None
    length = meta.length_s if isinstance(meta.length_s, (int, float)) and math.isfinite(meta.length_s) else 0.0
    return meta.date - dt.timedelta(seconds=max(0.0, float(length)))


def late_flags(replays: Sequence[ReplayMeta]) -> np.ndarray:
    """1 for plays started 40 min or more after the first play of their session (plays less than 20 min apart)."""
    starts = [started(m) for m in replays]
    order = sorted(range(len(replays)), key=lambda i: (starts[i] is None, starts[i] or dt.datetime.min))
    out = np.zeros(len(replays))
    start = prev = None
    for i in order:
        d = starts[i]
        if d is None:
            continue
        if prev is None or d - prev >= SESSION_GAP:
            start = d
        out[i] = float(d - start >= LATE_AFTER)
        prev = d
    return out


def merge(parts: Sequence[tuple[ReplayMeta, IrtGroups]]) -> Merged:
    """The :class:`Merged` table of these plays (each its meta and its own groups)."""
    kept = [(m, g) for m, g in parts if usable(m)]
    if not kept:
        return Merged(group({"kind": np.zeros(0, dtype=np.int64)}), used=0, left_out=len(parts))
    metas = [m for m, _ in kept]
    w, late = weights(metas), late_flags(metas)
    plays: dict[str, float] = {}
    for (_, g), weight in zip(kept, w, strict=True):
        for k, col in zip(K.SKILLS, B_COLUMNS, strict=True):
            if np.isfinite(getattr(g, col)).any():
                plays[k] = plays.get(k, 0.0) + float(weight)
        if (g.kind == K.ACCURACY).any():
            plays["acc"] = plays.get("acc", 0.0) + float(weight)
    columns = {c: np.concatenate([getattr(g, c) for _, g in kept]) for c in IrtGroups.names()}
    row_w = np.concatenate([np.full(len(g), x) for (_, g), x in zip(kept, w, strict=True)])
    row_late = np.concatenate([np.full(len(g), x) for (_, g), x in zip(kept, late, strict=True)])
    columns.pop("late")
    merged = group(columns, late=row_late, weight=row_w)
    return Merged(merged, plays=plays, used=len(kept), left_out=len(parts) - len(kept))
