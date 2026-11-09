"""What to play next: maps of the pool near the player's level that train what the goal needs."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence

from osu_coach.domain.numeric.values import finite_or_none
from osu_coach.domain.play_goals.evidence import MIN_MAPS, MIN_PLAYS, accuracy_range, comparable
from osu_coach.domain.play_goals.models import EvidenceRow, MapRow, Recommendation

DEMANDS = ("aim", "flow_aim", "speed", "reading", "sliders", "stamina")  # the pool's demand shares s_<skill>


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
    curve = sorted(row.get("pp_curve", []), key=lambda p: p["accuracy"])
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


def recommend(
    pool: Sequence[MapRow],
    rows: Sequence[EvidenceRow],
    goal: str,
    mods: Sequence[str],
    client: str,
    target: MapRow | None,
    focus: Sequence[str],
    min_pp: float | None = None,
    comfort: float | None = None,
) -> list[Recommendation]:
    """The maps to play next, best first; ``focus`` are the skills to train."""
    complete = [r for r in rows if r.completed and r.client == client]
    # The profile's comfort stars are what the rest of the app calls the player's level.
    base = comfort or (statistics.median(r.stars for r in complete) if complete else 2.0)
    nm_stars = {r["md5"]: r["stars"] for r in pool if r["mods"] == "NM" and r["client"] == client}
    result = []
    for row in pool:
        if row["mods"] not in mods or row["client"] != client:
            continue
        if goal == "farm" and row.get("status") not in ("ranked", "approved", 1, 2):
            continue
        if target and row["md5"] == target["md5"] and row["mods"] == target["mods"]:
            continue
        mod_rows = [r for r in complete if r.mods_name == row["mods"]]
        measured = len({r.beatmap_md5 for r in mod_rows}) >= MIN_MAPS
        # Unmeasured mods start from easy NM maps, and the modded map must be within that level too:
        # DT can turn a 5.5 star map into an 8.5 star one.
        level = statistics.median(r.stars for r in mod_rows) if measured else max(1.5, base - 0.3)
        delta = row["stars"] - level
        if not measured:
            delta = max(nm_stars.get(row["md5"], row["stars"]) - level, delta)
        if not -1.5 <= delta <= (0.2 if goal == "farm" else 0.5 if measured else 0):
            continue
        risk = _unrelated_risk(row, mod_rows or complete)  # with no plays of this mod: everything completed
        if risk > (2 if mod_rows else 1):
            continue
        estimates = accuracy_range(row, rows)
        peers = comparable(row, rows)
        same = [r for r in rows if r.beatmap_md5 == row["md5"] and r.mods_name == row["mods"] and r.client == client]
        practice = _practice_accuracy(row, delta, mod_rows, complete, peers if estimates else None, nm_stars)
        relevance = sum(finite_or_none(row.get("s_" + s)) or 0 for s in focus) / max(1, len(focus))
        if focus and relevance < 0.15:
            continue
        scenario = sampled_pp(row, practice)
        if min_pp and (scenario is None or scenario[0] < min_pp):
            continue
        clean_peers = len(peers) >= MIN_PLAYS and sum(bool(r.fc) for r in peers) / len(peers) >= 0.7
        ss = sampled_pp(row, 1.0)
        result.append(
            Recommendation(
                map=row,
                practice_accuracy=practice,
                accuracy=estimates,
                pp=scenario[0] if scenario else None,
                pp_ss=ss[0] if ss else None,
                pp_accuracy=scenario[1] if scenario else None,
                local_best_accuracy=max((r.accuracy for r in same if r.completed), default=None),
                achieved=any(r.fc and r.accuracy >= practice for r in same),
                stage="starter" if not measured else "stretch" if delta > 0.1 else "core",
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
            r.map["mods"],
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
    nm_stars: Mapping[str, float],
) -> float:
    """The accuracy to aim for. Easier than your level: aim high; at the edge of it: lower. Spans 99% down to 90%.
    Nearly clean plays of similar difficulty (``peers`` when they support an estimate) pull the target towards what
    you actually score."""
    scaled = 0.99 - 0.09 * min(1.0, max(0.0, (delta + 1.5) / 2.0))
    if peers is None:
        accuracy_rows = mod_rows if len(mod_rows) >= 3 else complete
        star_ref = row["stars"] if len(mod_rows) >= 3 else nm_stars.get(row["md5"], row["stars"])
        peers = [r for r in accuracy_rows if abs(r.stars - star_ref) <= 1.0]
    near = [r.accuracy for r in peers if r.breaks <= 2]
    practice = (scaled + statistics.median(near) + 0.01) / 2 if len(near) >= 3 else scaled
    return round(min(0.99, max(0.90, practice)), 2)
