"""Conservative, configuration-specific play evidence and goal objectives."""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from urllib.parse import urlsplit

from osu_coach.check import domain as check
from osu_coach.maps.goal_pool import CONFIGS

MIN_PLAYS = 10
MIN_MAPS = 5
RECENT_ATTEMPTS = 3

VERDICT_TONES = {
    "Already FCed": "good",
    "FC looks within reach": "good",
    "A stretch": "warn",
    "Beyond current reach": "bad",
    "Beyond current reach for now": "bad",
}


def number(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def sim_ok(meta: dict) -> bool:
    # lazer replays rarely match the header exactly; 90% agreement is enough to locate breaks.
    return meta.get("sim_match") is True or (number(meta.get("sim_agreement")) or 0) >= 0.9


def beatmap_id(value: str) -> int:
    value = value.strip()
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.netloc != "osu.ppy.sh":
        raise ValueError("Use an https://osu.ppy.sh beatmap difficulty link.")
    match = re.fullmatch(r"/(?:b|beatmaps)/([1-9][0-9]{0,9})/?", parsed.path)
    if not match and re.fullmatch(r"/beatmapsets/[1-9][0-9]*/?", parsed.path):
        match = re.fullmatch(r"osu/([1-9][0-9]{0,9})", parsed.fragment)
    if not match:
        raise ValueError("Choose a specific osu!standard difficulty, not just a beatmapset.")
    return int(match[1])


def configuration(meta: dict) -> str | None:
    bits = meta.get("mods")
    if not isinstance(bits, int) or meta.get("client") not in ("stable", "lazer"):
        return None
    bits &= ~1  # NoFail changes no difficulty
    if bits & 512:
        bits = (bits & ~512) | 64
    name = next((name for name, value in CONFIGS.items() if value == bits), None)
    if name is None or abs((number(meta.get("rate")) or 1) - (1.5 if bits & 64 else 1)) > 1e-6:
        return None
    if meta["client"] == "lazer":
        mods = meta.get("goal_lazer_mods")
        if not isinstance(mods, list):
            return None
        actual = 0
        for mod in mods:
            if not isinstance(mod, dict) or mod.get("acronym") not in ("EZ", "HD", "HR", "DT", "NC", "NF"):
                return None
            acronym = mod["acronym"]
            actual |= {"EZ": 2, "HD": 8, "HR": 16, "DT": 64, "NC": 64, "NF": 0}[acronym]
            extra = set(mod.get("settings") or {})
            if acronym == "EZ":
                extra -= {"retries"}
            if acronym in ("DT", "NC") and (mod.get("settings") or {}).get("speed_change") == 1.5:
                extra -= {"speed_change"}
            if extra:
                return None
        if actual != bits:
            return None
    return name


def full_combo(a) -> bool:
    m = a.meta
    return (
        bool(m.get("completed"))
        and m.get("n_played") == m.get("n_objects")
        and m.get("nmiss") == 0
        and m.get("sim_match") is True
        and check.events(a).empty
    )


def evidence(analyses: list, player: str | None) -> list[dict]:
    if player is None:
        return []
    seen, out = set(), []
    for a in analyses:
        m = a.meta
        mods = configuration(m)
        key = (m.get("beatmap_md5"), str(m.get("date")), m.get("score"))
        if m.get("player") != player or mods is None or key in seen or not sim_ok(m):
            continue
        if not all(number(m.get(k)) is not None for k in ("stars", "ar", "od", "bpm", "length_s", "accuracy")):
            continue
        seen.add(key)
        ns = a.objects[a.objects["played"] & (a.objects["kind"] != "spinner")]
        out.append(
            {
                **m,
                "mods_name": mods,
                "fc": full_combo(a),
                "breaks": len(check.events(a)),
                "stream_share": float((ns["pattern"] == "stream").mean()) if len(ns) else 0,
                "jump_share": float((ns["pattern"] == "jump").mean()) if len(ns) else 0,
            }
        )
    return out


def comparable(target: dict, rows: list[dict]) -> list[dict]:
    selected = []
    for row in rows:
        if row["mods_name"] != target["mods"] or row["client"] != target["client"] or not row.get("completed"):
            continue
        if row.get("n_played") != row.get("n_objects"):
            continue
        if any(abs(row[k] - target[k]) > gap for k, gap in (("stars", 0.6), ("ar", 1), ("od", 1), ("bpm", 25))):
            continue
        if not 0.5 <= row["length_s"] / max(1, target["length_s"]) <= 2:
            continue
        if any(abs(row.get(k, 0) - (number(target.get(k)) or 0)) > 0.25 for k in ("stream_share", "jump_share")):
            continue
        if any(
            number(row.get(k)) is not None
            and number(target.get(k)) is not None
            and abs(row[k] - target[k]) > max(0.5, target[k] * 0.35)
            for k in ("aim", "speed")
        ):
            continue
        selected.append(row)
    selected.sort(key=lambda r: str(r.get("date")), reverse=True)
    # One map cannot dominate the range, even if it has hundreds of retries.
    counts: Counter = Counter()
    balanced = []
    for row in selected:
        md5 = row["beatmap_md5"]
        if counts[md5] < 2:
            balanced.append(row)
            counts[md5] += 1
    return balanced[:60]


def accuracy_range(target: dict, rows: list[dict]) -> dict | None:
    peers = comparable(target, rows)
    maps = len({r["beatmap_md5"] for r in peers})
    if len(peers) < MIN_PLAYS or maps < MIN_MAPS:
        return None
    values = sorted(r["accuracy"] for r in peers)
    return {
        "low": values[math.floor((len(values) - 1) * 0.1)],
        "high": values[math.ceil((len(values) - 1) * 0.9)],
        "median": statistics.median(values),
        "plays": len(peers),
        "maps": maps,
        "explanation": "Middle 80% of the most recent available comparable completed plays, capped at two per map. "
        "An empirical estimate, not a maximum or a calibrated prediction interval.",
    }


def reachability(target: dict, rows: list[dict]) -> tuple[str, list[str], str]:
    same = [
        r
        for r in rows
        if r["beatmap_md5"] == target["md5"] and r["mods_name"] == target["mods"] and r["client"] == target["client"]
    ]
    if any(r["fc"] for r in same):
        return "Already FCed", ["A complete, verified no-break play exists for this map and configuration."], "moderate"
    peers = comparable(target, rows)
    if same:
        # Current form: an old, better run of the map must not hide that you play it worse now.
        recent = sorted(same, key=lambda r: str(r.get("date")), reverse=True)[:RECENT_ATTEMPTS]
        best = min(recent, key=lambda r: (not r["completed"], r["breaks"]))
        if best["completed"] and best["breaks"] <= 2:
            return (
                "FC looks within reach",
                [
                    f"Your best of the latest {len(recent)} attempt(s) has {best['breaks']} combo-breaking event(s).",
                    "This is a qualitative assessment, not an FC probability.",
                ],
                "limited",
            )
        verdict = "A stretch" if best["completed"] and best["breaks"] < 10 else "Beyond current reach for now"
        return (
            verdict,
            [
                f"Your best of the latest {len(recent)} attempt(s): {best['accuracy']:.1%} accuracy, {best['breaks']} combo-breaking event(s)"
                + ("" if best["completed"] else ", did not finish")
                + ".",
                "Based on your attempts of this map only.",
            ],
            "limited",
        )
    complete = [
        r for r in rows if r["completed"] and r["mods_name"] == target["mods"] and r["client"] == target["client"]
    ]
    if len({r["beatmap_md5"] for r in complete}) >= MIN_MAPS:
        base = statistics.median(r["stars"] for r in complete)
        speed = statistics.median(r["bpm"] for r in complete)
        # A star gap alone is not enough: demand plus demonstrated inability must agree.
        bad_attempts = len(same) >= 2 and all(not r["completed"] or r["breaks"] >= 10 for r in same)
        tempo_gap = target["bpm"] > speed * 1.25 and (number(target.get("stream_share")) or 0) > 0.15
        peak_gap = any(
            number(target.get(skill)) is not None
            and (values := [r[skill] for r in complete if number(r.get(skill)) is not None])
            and target[skill] > max(values) * 1.35
            for skill in ("aim", "speed")
        )
        if target["stars"] > base + 2 and (bad_attempts or tempo_gap or peak_gap):
            return (
                "Beyond current reach",
                [
                    f"The target is {target['stars'] - base:.1f} stars above your typical verified completed maps with these mods.",
                    "Its demands are outside your demonstrated range. Train the stepping stones before grinding FC attempts.",
                ],
                "limited",
            )
    if len(peers) >= MIN_PLAYS:
        return (
            "A stretch",
            [
                "Comparable plays support an accuracy estimate, but do not establish this map as a realistic FC yet.",
                "Use the practice objectives, then return with fresh attempts.",
            ],
            "moderate",
        )
    return (
        "Not enough evidence",
        [
            "Needs a verified attempt of this map or enough similar plays with these mods.",
        ],
        "unassessed",
    )


def skipped_attempts(analyses: list, rows: list[dict], player: str | None, target: dict) -> str | None:
    """Why the player's attempts of the target map are not usable evidence, or None if there are none."""
    kept = {r["key"] for r in rows}
    why: Counter = Counter()
    for a in analyses:
        m = a.meta
        if m.get("beatmap_md5") != target["md5"] or m.get("player") != player or a.key in kept:
            continue
        mods = f"+{m.get('mod_string') or 'NM'}"
        if m.get("client") != target["client"]:
            why[f"{mods} on osu!{m.get('client')}, target is osu!{target['client']}"] += 1
        elif not sim_ok(m):
            why["simulation did not match the replay result"] += 1
        elif configuration(m) is None:
            why[f"{mods} is not a supported mod setup"] += 1
        elif configuration(m) != target["mods"]:
            why[f"{mods}, target is +{target['mods']}"] += 1
        else:
            why["incomplete map or score data"] += 1
    if not why:
        return None
    return f"{sum(why.values())} attempt(s) of this map skipped: " + "; ".join(why) + "."


def blockers(analyses: list, target: dict) -> list[dict]:
    groups: dict[str, dict] = {}
    for a in analyses:
        m = a.meta
        if (
            m.get("beatmap_md5") != target["md5"]
            or configuration(m) != target["mods"]
            or m.get("client") != target["client"]
        ):
            continue
        for event in check.events(a).to_dict("records"):
            reason, pattern = event["reason"], event["pattern"]
            skill = (
                "sliders"
                if reason in ("follow", "released", "key_swap") or pattern == "slider"
                else "speed"
                if pattern in ("stream", "burst") and reason in ("late", "early", "no_tap")
                else "reading"
                if reason == "lost"
                else "accuracy"
                if reason in ("early", "late")
                else "flow_aim"
                if pattern == "spaced"
                else "aim"
            )
            group = groups.setdefault(skill, {"count": 0, "times": Counter(), "attempts": set()})
            group["count"] += 1
            group["times"][event["timestamp"]] += 1
            group["attempts"].add(a.key)
    labels = {
        "sliders": "Slider control",
        "speed": "Stream / burst tapping",
        "reading": "Tracking the next notes",
        "accuracy": "Hit timing",
        "flow_aim": "Spaced-stream aim",
        "aim": "Jump aim",
    }
    ranked = sorted(groups, key=lambda k: (-len(groups[k]["attempts"]), -groups[k]["count"], k))[:3]
    return [
        {
            "skill": skill,
            "title": labels[skill],
            "observed": True,
            "detail": f"{groups[skill]['count']} breaking event(s) across {len(groups[skill]['attempts'])} attempt(s). "
            "These are replay-derived patterns, not proof of a single underlying cause.",
            "timestamps": [t for t, _ in groups[skill]["times"].most_common(5)],
        }
        for skill in ranked
    ]


DYNAMICS = {
    "aim": ("Jumpy", "Jump aim"),
    "flow_aim": ("Flow aim", "Flow aim"),
    "speed": ("Streamy", "Streaming"),
    "reading": ("Reading-heavy", "Reading"),
    "sliders": ("Slider-heavy", "Sliders"),
    "stamina": ("Stamina-heavy", "Stamina"),
}


def dynamics(row: dict) -> str:
    """What kind of map this is: every strong demand, strongest first, or Balanced."""
    demand = sorted(((number(row.get("s_" + k)) or 0, k) for k in DYNAMICS), reverse=True)
    top = [k for value, k in demand[:3] if value >= 0.3]
    return " + ".join(DYNAMICS[k][0] for k in top) or "Balanced"


def lacking_focus(target: dict, skills: dict[str, float]) -> list[dict]:
    """The target's demands weighted by how weak the player is at them (skills: 0-1 scores)."""
    ranked = sorted(((number(target.get("s_" + k)) or 0) * (1 - skills.get(k, 0.5)), k) for k in DYNAMICS)[::-1]
    picked = [k for weight, k in ranked[:2] if weight >= 0.15] or [ranked[0][1]]
    return [
        {
            "skill": k,
            "title": DYNAMICS[k][1],
            "detail": f"This map leans on it; your score is {skills[k] * 100:.0f}/100."
            if k in skills
            else "This map leans on it; you have no score for it yet.",
            "observed": False,
            "timestamps": [],
        }
        for k in picked
    ]


def sampled_pp(row: dict, accuracy: float) -> tuple[float, float] | None:
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
    pool: list[dict],
    rows: list[dict],
    goal: str,
    mods: list[str],
    client: str,
    target: dict | None,
    focus: list[dict],
    min_pp: float | None = None,
    comfort: float | None = None,
) -> list[dict]:
    complete = [r for r in rows if r["completed"] and r["client"] == client]
    # The profile's comfort stars are what the rest of the app calls the player's level.
    base = comfort or (statistics.median(r["stars"] for r in complete) if complete else 2.0)
    nm_stars = {r["md5"]: r["stars"] for r in pool if r["mods"] == "NM" and r["client"] == client}
    result = []
    for row in pool:
        if row["mods"] not in mods or row["client"] != client:
            continue
        if goal == "farm" and row.get("status") not in ("ranked", "approved", 1, 2):
            continue
        if target and row["md5"] == target["md5"] and row["mods"] == target["mods"]:
            continue
        mod_rows = [r for r in complete if r["mods_name"] == row["mods"]]
        measured = len({r["beatmap_md5"] for r in mod_rows}) >= MIN_MAPS
        # Unmeasured mods start from easy NM maps, and the modded map must be within that level too:
        # DT can turn a 5.5 star map into an 8.5 star one.
        level = statistics.median(r["stars"] for r in mod_rows) if measured else max(1.5, base - 0.3)
        delta = row["stars"] - level
        if not measured:
            delta = max(nm_stars.get(row["md5"], row["stars"]) - level, delta)
        if not -1.5 <= delta <= (0.2 if goal == "farm" else 0.5 if measured else 0):
            continue
        # With no plays of this mod, compare against everything the player completed.
        reference = mod_rows or complete
        unrelated_risk = 0.0
        if reference:
            baseline_ar = statistics.median(r["ar"] for r in reference)
            unrelated_risk += max(0, row["ar"] - baseline_ar - 0.5)
            if (number(row.get("stream_share")) or 0) > 0.15:
                baseline_bpm = statistics.median(r["bpm"] for r in reference)
                unrelated_risk += max(0, row["bpm"] / max(1, baseline_bpm) - 1.05) * 4
        if unrelated_risk > (2 if mod_rows else 1):
            continue
        estimates = accuracy_range(row, rows)
        peers = comparable(row, rows)
        same = [
            r
            for r in rows
            if r["beatmap_md5"] == row["md5"] and r["mods_name"] == row["mods"] and r["client"] == client
        ]
        best = max((r["accuracy"] for r in same if r["completed"]), default=None)
        # Easier than your level: aim high; at the edge of it: lower. Spans 99% down to 90%. Nearly clean plays of
        # similar difficulty pull the target towards what you actually score.
        scaled = 0.99 - 0.09 * min(1.0, max(0.0, (delta + 1.5) / 2.0))
        accuracy_rows = mod_rows if len(mod_rows) >= 3 else complete
        star_ref = row["stars"] if len(mod_rows) >= 3 else nm_stars.get(row["md5"], row["stars"])
        near_pool = peers if estimates else [r for r in accuracy_rows if abs(r["stars"] - star_ref) <= 1.0]
        near = [r["accuracy"] for r in near_pool if r["breaks"] <= 2]
        if len(near) >= 3:
            practice = (scaled + statistics.median(near) + 0.01) / 2
        else:
            practice = scaled
        practice = round(min(0.99, max(0.90, practice)), 2)
        achieved = any(r["fc"] and r["accuracy"] >= practice for r in same)
        relevance = sum(number(row.get("s_" + b["skill"])) or 0 for b in focus) / max(1, len(focus))
        if focus and relevance < 0.15:
            continue
        skill_names = ", ".join(b["title"].lower() for b in focus) or (
            "HD reading"
            if "HD" in row["mods"]
            else "tempo and control"
            if "DT" in row["mods"]
            else "HR precision"
            if "HR" in row["mods"]
            else "consistent full-map play"
        )
        scenario = sampled_pp(row, practice)
        if min_pp and (scenario is None or scenario[0] < min_pp):
            continue
        clean_peers = len(peers) >= MIN_PLAYS and sum(bool(r["fc"]) for r in peers) / len(peers) >= 0.7
        projected = goal == "farm" and estimates is not None and clean_peers
        label = (
            ("Achievable FC scenario (estimate)" if projected else "Conditional FC scenario, not a forecast")
            if scenario
            else None
        )
        score = (
            (scenario[0] if scenario else 0) if goal == "farm" else (relevance * 3 - abs(delta + 0.3) - unrelated_risk)
        )
        result.append(
            {
                "map": {**row, "dynamics": dynamics(row)},
                "why": f"Trains {skill_names}.",
                "objective": f"Play +{row['mods']}, aim for {practice:.0%}, no combo breaks.",
                "step_up": "Pass twice, then move up.",
                "accuracy": estimates,
                "practice_accuracy": practice,
                "pp": scenario[0] if scenario else None,
                "pp_ss": (ss := sampled_pp(row, 1.0)) and ss[0],
                "pp_accuracy": scenario[1] if scenario else None,
                "pp_label": label,
                "local_best_accuracy": best,
                "achieved": achieved,
                "stage": "Starter" if not measured else "Stretch" if delta > 0.1 else "Core",
                "_score": score,
                "_projected": projected,
            }
        )
    result.sort(
        key=lambda r: (
            r["achieved"],  # targets you already met go last
            not r["_projected"] if goal == "farm" else False,
            -r["_score"],
            r["map"]["md5"],
            r["map"]["mods"],
        )
    )
    # Keep the first screen varied; additional configurations of one map remain available later.
    first, rest, seen = [], [], set()
    for row in result:
        if row["map"]["md5"] in seen:
            rest.append(row)
        else:
            seen.add(row["map"]["md5"])
            first.append(row)
    return (first + rest)[:100]
