"""Key numbers of the local player's profile, for before/after comparisons of the analysis.

    python dev_tools/numbers.py [OUT.json]

Analyses the replays of the osu! installs on this computer (cached analyses are reused) and prints, for
four selections (all replays / best replays, all time / last 7 days): the detected level, miss-cause shares,
stamina, stream comfort BPM and the skill scores. The selections are made here (not with the app's own
filters), so the same replays go into the old and the new profile code.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys

from osu_coach.infrastructure.filesystem import locate
from osu_coach.infrastructure.filesystem.library import Library
from osu_coach.domain.profile import build_profile


def best_of(analyses):
    best = {}
    for a in analyses:
        m = a.meta
        if not m.get("completed"):
            continue
        k = (m.get("beatmap_md5"), round(float(m.get("rate") or 1.0), 3))
        cur = best.get(k)
        if cur is None or (m.get("score") or 0, m.get("accuracy") or 0) > (cur.meta.get("score") or 0,
                                                                         cur.meta.get("accuracy") or 0):
            best[k] = a
    return list(best.values())


def recent(analyses, days):
    newest = max(a.meta["date"] for a in analyses)
    since = newest - dt.timedelta(days=days)
    return [a for a in analyses if a.meta["date"] >= since]


def _r(v, d=1):
    try:
        return None if v is None or math.isnan(v) else round(float(v), d)
    except TypeError:
        return v


def numbers(p) -> dict:
    total = sum(p.miss_breakdown.values()) or 1
    lv = p.levels
    st = p.skills.get("stamina", {})
    return {
        "replays": p.overview["replays"],
        "level": _r(lv.get("level_stars", lv.get("comfort_stars")), 2),
        "comfort_stars": _r(lv.get("comfort_stars"), 2),
        "miss_shares": {k: round(v / total * 100) for k, v in sorted(p.miss_breakdown.items(), key=lambda kv: -kv[1])},
        "stamina": {"score": _r(st.get("score"), 0), "n": _r(st.get("n"), 0),
                    "early": _r(st.get("early_miss_rate"), 3), "late": _r(st.get("late_miss_rate"), 3)},
        "stream_comfort_bpm": p.tapping.get("comfort_bpm"), "stream_limit_bpm": p.tapping.get("limit_bpm"),
        "ur": _r(p.overview.get("ur"), 0),
        "skills": {k: _r(v.get("score"), 0) for k, v in p.skills.items()},
    }


def main():
    lib = Library()
    for inst in locate.find_installs():
        lib.add_install(inst)
    player = lib.players()[0][0]
    refs = lib.eligible(player)
    lib.fetch_missing(lib.missing_maps(refs))
    analyses, errors = lib.analyze(refs)
    out = {"player": player, "analysed": len(analyses), "skipped": len(errors)}
    for name, sel in (("all", analyses), ("best", best_of(analyses)), ("all_7d", recent(analyses, 7)),
                      ("best_7d", best_of(recent(analyses, 7)))):
        out[name] = numbers(build_profile(sel))
    text = json.dumps(out, indent=1, default=str)
    print(text)
    if len(sys.argv) > 1:
        open(sys.argv[1], "w", encoding="utf-8").write(text)


if __name__ == "__main__":
    main()
