"""How reachable an FC of the target is, from the player's attempts of it and their other verified plays."""

from __future__ import annotations

import statistics
from collections.abc import Sequence

from osu_coach.domain.numeric.values import finite_or_none
from osu_coach.domain.play_goals.evidence import MIN_MAPS, MIN_PLAYS, comparable, same_map
from osu_coach.domain.play_goals.models import EvidenceRow, MapRow, Reach, Reason

RECENT_ATTEMPTS = 3


def reachability(target: MapRow, rows: Sequence[EvidenceRow]) -> Reach:
    same = same_map(target, rows)
    if any(r.fc for r in same):
        return Reach("fc_done", (Reason("fc_exists"),), "moderate")
    peers = comparable(target, rows)
    if same:
        # Current form: an old, better run of the map must not hide that you play it worse now.
        recent = sorted(same, key=lambda r: r.date, reverse=True)[:RECENT_ATTEMPTS]
        best = min(recent, key=lambda r: (not r.completed, r.breaks))
        if best.completed and best.breaks <= 2:
            return Reach(
                "fc_near", (Reason("recent_best_breaks", (len(recent), best.breaks)), Reason("qualitative")), "limited"
            )
        verdict = "stretch" if best.completed and best.breaks < 10 else "beyond_for_now"
        return Reach(
            verdict,
            (
                Reason("recent_best", (len(recent), best.accuracy, best.breaks, best.completed)),
                Reason("own_attempts_only"),
            ),
            "limited",
        )
    complete = [r for r in rows if r.completed and r.mods_name == target["mods"] and r.client == target["client"]]
    if len({r.beatmap_md5 for r in complete}) >= MIN_MAPS:
        base = statistics.median(r.stars for r in complete)
        speed = statistics.median(r.bpm for r in complete)
        # A star gap alone is not enough: demand plus demonstrated inability must agree.
        bad_attempts = len(same) >= 2 and all(not r.completed or r.breaks >= 10 for r in same)
        tempo_gap = target["bpm"] > speed * 1.25 and (finite_or_none(target.get("stream_share")) or 0) > 0.15
        peak_gap = any(
            finite_or_none(target.get(skill)) is not None
            and (values := [getattr(r, skill) for r in complete if finite_or_none(getattr(r, skill)) is not None])
            and target[skill] > max(values) * 1.35
            for skill in ("aim", "speed")
        )
        if target["stars"] > base + 2 and (bad_attempts or tempo_gap or peak_gap):
            return Reach(
                "beyond", (Reason("stars_above", (target["stars"] - base,)), Reason("outside_range")), "limited"
            )
    if len(peers) >= MIN_PLAYS:
        return Reach("stretch", (Reason("peers_no_fc"), Reason("practice_first")), "moderate")
    return Reach("unknown", (Reason("needs_evidence"),), "unassessed")
