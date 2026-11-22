"""What to play next: maps of the pool near the player's level that train what the goal needs."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from osu_coach.domain.numeric.values import finite_or_none
from osu_coach.domain.play_goals.evidence import MIN_MAPS, MIN_PLAYS, comparable, estimate
from osu_coach.domain.play_goals.models import EvidenceRow, MapRow, Recommendation

DEMANDS = ("aim", "flow_aim", "speed", "reading", "sliders", "stamina")  # the pool's demand shares s_<skill>
BELOW = 1.5  # stars below the level a map may be
ABOVE = 0.5  # and above it, in a configuration the player has played enough of
FARM_ABOVE = 0.2  # Farm PP: above it


def dynamics(row: MapRow) -> list[str]:
    """What kind of map this is: every strong demand, strongest first (empty: balanced)."""
    demand = sorted(((finite_or_none(row.get("s_" + k)) or 0, k) for k in DEMANDS), reverse=True)
    return [k for value, k in demand[:3] if value >= 0.3]


def lacking_focus(target: MapRow, skills: Mapping[str, float]) -> list[str]:
    """The target's demands weighted by how weak the player is at them (skills: 0-1 scores)."""
    ranked = sorted(((finite_or_none(target.get("s_" + k)) or 0) * (1 - skills.get(k, 0.5)), k) for k in DEMANDS)[::-1]
    return [k for weight, k in ranked[:2] if weight >= 0.15] or [ranked[0][1]]


def sampled_pp(row: MapRow, accuracy: float) -> tuple[float, float] | None:
    """PP of a full combo at ``accuracy``, between the two stored curve points (PP grows ~exponentially with accuracy)."""
    curve = sorted(row.get("pp_curve") or [], key=lambda p: p["accuracy"])
    below = [p for p in curve if p["accuracy"] <= accuracy + 1e-9]
    above = [p for p in curve if p["accuracy"] >= accuracy - 1e-9]
    if not below or not above:
        return None
    lo, hi = below[-1], above[0]
    if hi["accuracy"] - lo["accuracy"] < 1e-9:
        return lo["pp"], accuracy
    t = (accuracy - lo["accuracy"]) / (hi["accuracy"] - lo["accuracy"])
    if lo["pp"] > 0 and hi["pp"] > 0:
        return math.exp(math.log(lo["pp"]) * (1 - t) + math.log(hi["pp"]) * t), accuracy
    return lo["pp"] * (1 - t) + hi["pp"] * t, accuracy


@dataclass(frozen=True)
class Level:
    """The stars a configuration's maps are picked around: the median of the player's completed maps in it once they
    have played enough of them (``measured``), else just under their level (a starting point). A map's stars in the
    configuration must lie in ``lowest``..``highest``; while it isn't measured, its stars without mods too (DT can
    turn a 5.5 star map into an 8.5 star one)."""

    stars: float
    measured: bool
    lowest: float
    highest: float


def level(config: str, rows: Sequence[EvidenceRow], client: str, goal: str, comfort: float | None = None) -> Level:
    """The level a goal's maps in ``config`` are picked around. ``comfort``: the profile's comfort stars, what the rest
    of the app calls the player's level (else the median of their completed maps)."""
    complete = [r for r in rows if r.completed and r.client == client]
    base = comfort or (statistics.median(r.stars for r in complete) if complete else 2.0)
    mod_rows = [r for r in complete if r.config == config]
    measured = len({r.beatmap_md5 for r in mod_rows}) >= MIN_MAPS
    stars = statistics.median(r.stars for r in mod_rows) if measured else max(1.5, base - 0.3)
    above = FARM_ABOVE if goal == "farm" else ABOVE if measured else 0.0
    return Level(stars, measured, stars - BELOW, stars + above)


def recommend(
    pool: Sequence[MapRow],
    rows: Sequence[EvidenceRow],
    goal: str,
    configs: Sequence[str],
    client: str,
    target: MapRow | None,
    focus: Sequence[str],
    min_pp: float | None = None,
    comfort: float | None = None,
) -> list[Recommendation]:
    """The maps to play next, best first; ``configs`` are the configurations to play them in, ``focus`` the skills to
    train."""
    complete = [r for r in rows if r.completed and r.client == client]
    levels = {c: level(c, rows, client, goal, comfort) for c in configs}
    by_config: dict[str, list[EvidenceRow]] = defaultdict(list)
    for r in complete:
        by_config[r.config].append(r)
    same: dict[tuple[str, str], list[EvidenceRow]] = defaultdict(list)
    for r in rows:
        if r.client == client:
            same[r.beatmap_md5, r.config].append(r)
    result = []
    for row in pool:
        config = row["config"]
        if config not in levels or row["client"] != client:
            continue
        if goal == "farm" and row.get("status") not in ("ranked", "approved", 1, 2):
            continue
        if target and row["md5"] == target["md5"] and config == target["config"]:
            continue
        lv = levels[config]
        mod_rows = by_config[config]
        nm_stars = finite_or_none(row.get("stars_nm"))
        delta = row["stars"] - lv.stars
        if not lv.measured and nm_stars is not None:
            delta = max(nm_stars - lv.stars, delta)
        if not lv.lowest - lv.stars <= delta <= lv.highest - lv.stars:
            continue
        risk = _unrelated_risk(row, mod_rows or complete)  # with no plays of this mod: everything completed
        if risk > (2 if mod_rows else 1):
            continue
        relevance = sum(finite_or_none(row.get("s_" + s)) or 0 for s in focus) / max(1, len(focus))
        if focus and relevance < 0.15:
            continue
        peers = comparable(row, rows)
        estimates = estimate(peers)
        practice = _practice_accuracy(row, delta, mod_rows, complete, peers if estimates else None)
        scenario = sampled_pp(row, practice)
        if min_pp and (scenario is None or scenario[0] < min_pp):
            continue
        clean_peers = len(peers) >= MIN_PLAYS and sum(bool(r.fc) for r in peers) / len(peers) >= 0.7
        ss = sampled_pp(row, 1.0)
        played = same[row["md5"], config]
        result.append(
            Recommendation(
                map=row,
                practice_accuracy=practice,
                accuracy=estimates,
                pp=scenario[0] if scenario else None,
                pp_ss=ss[0] if ss else None,
                pp_accuracy=scenario[1] if scenario else None,
                local_best_accuracy=max((r.accuracy for r in played if r.completed), default=None),
                achieved=any(r.fc and r.accuracy >= practice for r in played),
                stage="starter" if not lv.measured else "stretch" if delta > 0.1 else "core",
                projected=goal == "farm" and estimates is not None and clean_peers,
                score=(scenario[0] if scenario else 0) if goal == "farm" else (relevance * 3 - abs(delta + 0.3) - risk),
            )
        )
    result.sort(
        key=lambda r: (
            r.achieved,  # targets you already met go last
            not r.projected if goal == "farm" else False,
            -r.score,
            r.map["md5"],
            r.map["config"],
        )
    )
    # Keep the first screen varied; additional configurations of one map remain available later.
    first, rest, seen = [], [], set()
    for rec in result:
        if rec.map["md5"] in seen:
            rest.append(rec)
        else:
            seen.add(rec.map["md5"])
            first.append(rec)
    return (first + rest)[:100]


def _unrelated_risk(row: MapRow, reference: Sequence[EvidenceRow]) -> float:
    """How far the map's AR and stream tempo are above what the player usually plays."""
    if not reference:
        return 0.0
    risk = max(0, row["ar"] - statistics.median(r.ar for r in reference) - 0.5)
    if (finite_or_none(row.get("stream_share")) or 0) > 0.15:
        baseline_bpm = statistics.median(r.bpm for r in reference)
        risk += max(0, row["bpm"] / max(1, baseline_bpm) - 1.05) * 4
    return risk


def _practice_accuracy(
    row: MapRow,
    delta: float,
    mod_rows: Sequence[EvidenceRow],
    complete: Sequence[EvidenceRow],
    peers: Sequence[EvidenceRow] | None,
) -> float:
    """The accuracy to aim for. Easier than your level: aim high; at the edge of it: lower. Spans 99% down to 90%.
    Nearly clean plays of similar difficulty (``peers`` when they support an estimate) pull the target towards what
    you actually score."""
    scaled = float(practice_scale(delta))
    if peers is None:
        accuracy_rows = mod_rows if len(mod_rows) >= 3 else complete
        star_ref = row["stars"] if len(mod_rows) >= 3 else finite_or_none(row.get("stars_nm")) or row["stars"]
        peers = [r for r in accuracy_rows if abs(r.stars - star_ref) <= 1.0]
    near = [r.accuracy for r in peers if r.breaks <= 2]
    practice = (scaled + statistics.median(near) + 0.01) / 2 if len(near) >= 3 else scaled
    return round(min(0.99, max(0.90, practice)), 2)


def practice_scale(delta):
    """The accuracy to aim for from difficulty alone: 99% far below the level, 90% at the top of the window (of a
    number, or of each of an array of them)."""
    return 0.99 - 0.09 * np.clip((np.asarray(delta, dtype=float) + BELOW) / 2.0, 0.0, 1.0)
