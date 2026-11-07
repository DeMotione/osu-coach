"""Consistency: how steady the plays are, and the consistency rating at a star rating."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from osu_coach.domain.analysis.models import ReplayMeta
from osu_coach.domain.numeric.values import finite_or_none
from osu_coach.domain.player.messages import Message
from osu_coach.domain.player.records import SkillRating

# ------------------------------------------------------------------ consistency at a star rating
STAR_MIN_MAPS = 8  # different maps needed before a star rating has a score; more = a more reliable score
STAR_SPAN = 1.0  # consistency at X★ uses the maps from X − STAR_SPAN up to X: never harder ones
STAR_EASY_WEIGHT = 0.5  # weight of a map STAR_SPAN easier than X (one at X = 1): easy maps can't carry the score
ACC_BAD, ACC_GOOD = 0.88, 0.94  # accuracy scale: 88% → 0, 94% → 1
COMBO_NONE = 0.10  # share of the map's max combo worth nothing: missing so much the combo never builds up
COMBO_HELD = 0.30  # combo scale value (≈20% of the max combo) below which a map's score fades to 0 at COMBO_NONE
BEST_WEIGHT = 0.7  # the better of combo and accuracy carries the score; both good = top score
SWING_WEIGHT = 0.5  # consistency = usual map score − this × its swing between maps
FULL_COMBO = 0.98  # share of the map's max combo (no misses) that counts as a full combo


def combo_scale(share):
    """How well the combo is held, 0–1, on a log scale from ``COMBO_NONE`` of the max combo (0) to a full combo (1):
    20% = 0.30, 30% = 0.48, 50% = 0.70, 70% = 0.85. Holding big parts of a map counts, not only full combos."""
    share = np.maximum(np.asarray(share, dtype=float), 1e-6)
    return np.clip(np.log10(share / COMBO_NONE) / np.log10(1 / COMBO_NONE), 0, 1)


def map_score(combo_share, accuracy):
    """0–1 for one play: the better of combo held (:func:`combo_scale`) and accuracy (88–94% scale) counts 70%, the
    other 30%, and the score fades to 0 when less than about 20% of the combo is held (10% or less = 0). 30% of the
    combo at 93% = 0.73, a full combo at 90% = 0.80."""
    combo = combo_scale(combo_share)
    acc = np.clip((np.asarray(accuracy, dtype=float) - ACC_BAD) / (ACC_GOOD - ACC_BAD), 0, 1)
    both = BEST_WEIGHT * np.maximum(combo, acc) + (1 - BEST_WEIGHT) * np.minimum(combo, acc)
    return both * np.minimum(1.0, combo / COMBO_HELD)


@dataclass(frozen=True, slots=True)
class ScoredPlay:
    """A play counted for the consistency at a star rating."""

    map: str  # beatmap md5
    combo: float  # share of the map's max combo held, 0–1
    map_score: float
    weight: float  # 1 at the star rating, STAR_EASY_WEIGHT a span easier
    full: float  # 1 for a full combo
    accuracy: float


def _finite(v) -> bool:
    return finite_or_none(v) is not None


def _plays_up_to(plays: Sequence[ReplayMeta] | None, stars: float) -> list[ScoredPlay]:
    """The plays of maps from ``stars`` − ``STAR_SPAN`` up to ``stars`` (star rating with mods), each once, scored by
    :func:`map_score`."""
    out, seen = [], set()
    for m in plays or ():
        if m.key in seen:
            continue
        seen.add(m.key)
        top = m.map_max_combo
        if not (_finite(m.stars) and _finite(m.accuracy) and _finite(top) and top > 0):
            continue
        if not stars - STAR_SPAN <= m.stars <= stars + 1e-9:
            continue
        combo = min(max((m.max_combo or 0) / top, 0.0), 1.0)
        out.append(
            ScoredPlay(
                map=str(m.beatmap_md5),
                combo=combo,
                map_score=float(map_score(combo, m.accuracy)),
                weight=1 - (1 - STAR_EASY_WEIGHT) * (stars - m.stars) / STAR_SPAN,
                full=float(combo >= FULL_COMBO and not (m.nmiss or 0)),
                accuracy=float(m.accuracy),
            )
        )
    return out


def star_consistency(plays: Sequence[ReplayMeta] | None, stars: float | None, *, comfort: bool = False) -> SkillRating:
    """How steadily combo and accuracy hold from map to map at the star rating ``stars``: the maps from a star below
    it up to it (6.2★: 5.2–6.2★, with mods; harder maps never count), every play scored by :func:`map_score`, each
    map once (the average of its plays, so retrying one map can't carry the score) and weighted by how close it is
    to ``stars``. Consistency = the usual map score − half its swing between maps. Scored from ``STAR_MIN_MAPS``
    different maps; until then ``needs`` says what to play. ``comfort``: ``stars`` is the comfort level (wording)."""
    if stars is None or not math.isfinite(stars):
        return SkillRating(
            score=None,
            maps=0,
            plays=0,
            min_maps=STAR_MIN_MAPS,
            needs=Message("comfort_first", {"maps": STAR_MIN_MAPS}),
            reason=Message("not_enough_data"),
        )
    low, high = max(0.0, stars - STAR_SPAN), stars
    scored = _plays_up_to(plays, stars)
    by_map: dict[str, list[ScoredPlay]] = {}
    for s in scored:
        by_map.setdefault(s.map, []).append(s)
    maps = sorted(by_map)

    def mean(field: str) -> np.ndarray:
        return np.array([np.mean([getattr(s, field) for s in by_map[k]]) for k in maps], dtype=float)

    found = {"low": low, "high": high, "maps": len(maps), "plays": len(scored), "min_maps": STAR_MIN_MAPS}
    if len(maps) < STAR_MIN_MAPS:
        needs = Message(
            "consistency_maps",
            {
                "more": STAR_MIN_MAPS - len(maps),
                "low": low,
                "high": high,
                "stars": stars,
                "comfort": comfort,
                "maps": STAR_MIN_MAPS,
                "so_far": len(maps),
            },
        )
        return SkillRating(score=None, needs=needs, reason=Message("not_enough_data"), **found)
    scores, weights, combo = mean("map_score"), mean("weight"), mean("combo")
    usual = float(np.average(scores, weights=weights))
    swing = float(np.sqrt(np.average((scores - usual) ** 2, weights=weights)))
    return SkillRating(
        score=round(100 * float(np.clip(usual - SWING_WEIGHT * swing, 0, 1)), 1),
        map_score=usual,
        swing=swing,
        weak_maps=int((combo < 0.2).sum()),
        mean_combo=float(np.average(combo, weights=weights)),
        full_combo_share=float(np.average(mean("full"), weights=weights)),
        mean_accuracy=float(np.average(mean("accuracy"), weights=weights)),
        reason=Message("consistency_held", {"maps": len(maps), "low": low, "high": high}),
        **found,
    )
