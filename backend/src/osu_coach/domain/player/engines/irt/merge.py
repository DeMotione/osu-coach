"""All plays' item groups added up, each play weighted by recency and the retry caps, sessions flagged.

Spec and why it differs from it: docs/star-scale-irt.md.
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
    """The merged groups, each used play's own groups (and stars), and how many plays were used."""

    groups: IrtGroups
    plays: dict[str, float] = field(default_factory=dict)
    used: int = 0
    left_out: int = 0
    parts: tuple[IrtGroups, ...] = ()  # every used play's own groups, weighted and session-flagged
    part_stars: tuple[float, ...] = ()  # ... and its map's star rating (with mods)


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
    """Each play's weight: recency × min(1, 3/N_setup, 5/N_set)."""
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
    """When the play started (a replay is saved at its end)."""
    if meta.date is None:
        return None
    length = meta.length_s if isinstance(meta.length_s, (int, float)) and math.isfinite(meta.length_s) else 0.0
    return meta.date - dt.timedelta(seconds=max(0.0, float(length)))


def late_flags(replays: Sequence[ReplayMeta]) -> np.ndarray:
    """1 for plays started 40+ min into their session."""
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
    """The merged table of these plays."""
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
    own = tuple(
        g.replace(n=g.n * x, f_a=g.f_a * x, f_b=g.f_b * x, f_t=g.f_t * x, late=np.full(len(g), lt))
        for (_, g), x, lt in zip(kept, w, late, strict=True)
    )
    columns = {c: np.concatenate([getattr(g, c) for g in own]) for c in IrtGroups.names()}
    row_late = columns.pop("late")
    merged = group(columns, late=row_late)
    stars = tuple(float(m.stars) if m.stars is not None else float("nan") for m in metas)
    return Merged(merged, plays=plays, used=len(kept), left_out=len(parts) - len(kept), parts=own, part_stars=stars)
