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


def number(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def beatmap_id(value: str) -> int:
    value = value.strip()
    if re.fullmatch(r"[1-9][0-9]{0,9}", value):
        return int(value)
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.netloc != "osu.ppy.sh":
        raise ValueError("Use a difficulty ID or an https://osu.ppy.sh beatmap difficulty URL.")
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
            if not isinstance(mod, dict) or mod.get("acronym") not in ("HD", "HR", "DT", "NC"):
                return None
            actual |= {"HD": 8, "HR": 16, "DT": 64, "NC": 64}[mod["acronym"]]
            settings = mod.get("settings") or {}
            if settings and (set(settings) != {"speed_change"} or settings["speed_change"] != 1.5):
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
        if m.get("player") != player or mods is None or key in seen or m.get("sim_match") is not True:
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
        best = min(same, key=lambda r: (not r["completed"], r["breaks"]))
        if best["completed"] and best["breaks"] <= 2:
            return (
                "FC looks within reach",
                [
                    f"Your best verified attempt has {best['breaks']} combo-breaking event(s).",
                    "This is a qualitative assessment, not an FC probability.",
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
            "An FC assessment needs verified same-map attempts or enough comparable plays with these mods.",
            "Analyse recent replays for this player. No FC odds or maximum accuracy are inferred from global ratings.",
        ],
        "unassessed",
    )


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


def sampled_pp(row: dict, accuracy: float) -> tuple[float, float] | None:
    samples = [v for v in row.get("pp_curve", []) if v["accuracy"] <= accuracy + 1e-9]
    if not samples:
        return None
    point = max(samples, key=lambda p: p["accuracy"])
    return point["pp"], point["accuracy"]


def recommend(
    pool: list[dict], rows: list[dict], goal: str, mods: list[str], client: str, target: dict | None, focus: list[dict]
) -> list[dict]:
    complete = [r for r in rows if r["completed"] and r["client"] == client]
    base = statistics.median(r["stars"] for r in complete) if complete else 2.0
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
        level = (
            statistics.median(r["stars"] for r in mod_rows)
            if measured
            else max(1.5, base - (0.8 if row["mods"] != "NM" else 0.3))
        )
        delta = row["stars"] - level
        if not -1.5 <= delta <= (0.5 if measured else 0):
            continue
        unrelated_risk = 0.0
        if mod_rows:
            baseline_ar = statistics.median(r["ar"] for r in mod_rows)
            unrelated_risk += max(0, row["ar"] - baseline_ar - 0.5)
            if (number(row.get("stream_share")) or 0) > 0.15:
                baseline_bpm = statistics.median(r["bpm"] for r in mod_rows)
                unrelated_risk += max(0, row["bpm"] / max(1, baseline_bpm) - 1.05) * 4
        if unrelated_risk > 2:
            continue
        estimates = accuracy_range(row, rows)
        peers = comparable(row, rows)
        same = [
            r
            for r in rows
            if r["beatmap_md5"] == row["md5"] and r["mods_name"] == row["mods"] and r["client"] == client
        ]
        best = max((r["accuracy"] for r in same if r["completed"]), default=None)
        practice = min(0.99, round((estimates["median"] if estimates else 0.95), 2))
        achieved = any(r["fc"] and r["accuracy"] >= practice for r in same)
        relevance = sum(number(row.get("s_" + b["skill"])) or 0 for b in focus) / max(1, len(focus))
        if focus and relevance < 0.15:
            continue
        skill_names = ", ".join(b["title"].lower() for b in focus) or (
            "HD reading"
            if row["mods"] == "HD"
            else "tempo and control"
            if "DT" in row["mods"]
            else "consistent full-map play"
        )
        scenario = sampled_pp(row, practice)
        clean_peers = len(peers) >= MIN_PLAYS and sum(bool(r["fc"]) for r in peers) / len(peers) >= 0.7
        projected = goal == "farm" and estimates is not None and clean_peers
        label = (
            ("Achievable FC scenario (estimate)" if projected else "Conditional FC scenario, not a forecast")
            if scenario
            else None
        )
        score = (
            (scenario[0] if projected and scenario else 0)
            if goal == "farm"
            else (relevance * 3 - abs(delta + 0.3) - unrelated_risk)
        )
        result.append(
            {
                "map": row,
                "why": f"Trains {skill_names} at {'a demonstrated' if measured else 'an unassessed starter'} level.",
                "objective": f"Play +{row['mods']}; aim for {practice:.0%} accuracy and no combo breaks. "
                + (
                    "This is a practice objective, not predicted accuracy."
                    if estimates is None
                    else "The estimate describes comparable plays, not a guarantee."
                ),
                "step_up": "After two complete plays meeting the objective, try the next difficulty or return to your target.",
                "accuracy": estimates,
                "practice_accuracy": practice,
                "pp": scenario[0] if scenario else None,
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
            r["achieved"],
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
