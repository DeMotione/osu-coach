"""The skill ratings: comfort-relative replay abilities, adapted from osu-skill-lab.

Each skill is scored against what is typical at the player's comfort level (50 = typical), not against other
players and not as a full-combo chance. A skill stays ``None`` when the replays don't cover or challenge it enough.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from osu_coach.analysis.skill_scale import SPEED_POINTS, expected_speed_bpm
from osu_coach.profile.domain.aim import aim_values, flow_values
from osu_coach.profile.domain.consistency import star_consistency
from osu_coach.profile.domain.demand import log_demand
from osu_coach.profile.domain.levels import RECENT_DAYS, RECENT_MIN, replay_weight
from osu_coach.profile.domain.reading import reading_values
from osu_coach.profile.domain.sliders import slider_difficulty
from osu_coach.profile.domain.stamina import tempo_curve
from osu_coach.profile.domain.stats import _map_key, played_notes
from osu_coach.profile.domain.tapping import speed_values

MIN_MAPS = 3
RANK_DECAY = 0.95
POINTS = {
    "aim": 25,
    "flow_aim": 25,
    "speed": SPEED_POINTS,
    "stamina": 75,
    "accuracy": 25,
    "sliders": 25,
    "reading": 25,
    "consistency": 0,  # not on this scale: combo and accuracy held per star rating (star_consistency)
}
STAMINA_SHARES = {10: 0.55, 30: 0.47, 60: 0.41, 120: 0.38, 300: 0.33}
ACCURACY_SIGMA_MS = (79.5 - 6 * 8) / 1.959963984540054
ACCURACY_LOW_SIGMA_MS = (79.5 - 6 * 8) / 1.6448536269514722
ACCURACY_TRANSITION_STARS = 5.5
# Slider control: what the 30 hardest held sliders of a typical 6★ map score (slider_difficulty), measured on 38 real
# maps of 5.7–7★ normalised to 6★ along the pool's slider curve (median 19.1, middle half 15–25). Harder maps ask for
# more as their sliders get faster (demand.log_demand), about 15% per ★ around 6★ — the old 40 × 2^((★−6)/3) asked for
# twice as much at 6★, so most players who don't break sliders were never "tested" (#54).
SLIDERS_AT_6 = 19.0


def comfort(metas: pd.DataFrame) -> float | None:
    """Recent, clean, distinct map/mod completions; interpolated 75th percentile."""
    if metas.empty or "date" not in metas:
        return None
    m = metas.copy()
    m["_date"] = pd.to_datetime(m["date"], utc=True, errors="coerce")
    m = m.dropna(subset=["_date"]).sort_values("_date", ascending=False)
    if m.empty:
        return None
    recent = m[m["_date"] >= m["_date"].iloc[0] - pd.Timedelta(days=RECENT_DAYS)]
    if len(recent) < RECENT_MIN:
        recent = m.head(RECENT_MIN)
    ok = recent["completed"].astype(bool) & (100 * recent["head_misses"] / recent["n_objects"].clip(lower=1) <= 2)
    good = recent[ok].dropna(subset=["stars"])
    if good.empty:
        return None
    keys = good["beatmap_md5"].astype(str) + ":" + good["mods"].astype(str)
    values = good.groupby(keys)["stars"].median()
    return float(values.quantile(0.75)) if len(values) >= MIN_MAPS else None


def _expected(skill: str, theta: float, *, duration: int | None = None) -> float:
    bpm = min(300.0, max(120.0, 120 + 15 * theta))
    return {
        "aim": 17.5 * 2 ** ((theta - 6) / 12),
        "flow_aim": 11 * 2 ** ((theta - 6) / 12),
        "speed": expected_speed_bpm(theta),
        "stamina": bpm * STAMINA_SHARES[duration] if duration else math.nan,
        "sliders": SLIDERS_AT_6 * 2 ** (log_demand("sliders", theta) - log_demand("sliders", 6.0)),
        "reading": 0.95**8,
    }.get(skill, math.nan)


# Slider control read about a tenth too high for everyone after #54 lowered its reference: its scores are scaled down
SCORE_FACTOR = {"sliders": 0.9}


def _score(skill: str, value: float | None, expected: float, *, inverse: bool = False) -> float | None:
    if value is None or not math.isfinite(value) or not math.isfinite(expected) or expected <= 0:
        return None
    ratio = max(value, 1e-6) / expected
    score = np.clip(50 + (-1 if inverse else 1) * POINTS[skill] * math.log2(ratio), 0, 100)
    return round(float(score * SCORE_FACTOR.get(skill, 1.0)), 1)


def _accuracy_sigma(theta: float) -> float:
    """At 4.5★/OD 8, assume 90% 300s; retain the old reference from 5.5★ up."""
    low_stars = max(0.0, ACCURACY_TRANSITION_STARS - theta)
    return ACCURACY_SIGMA_MS * (ACCURACY_LOW_SIGMA_MS / ACCURACY_SIGMA_MS) ** low_stars


def _accuracy_expected(windows: list[tuple[float, float]], theta: float) -> float:
    sigma = _accuracy_sigma(theta)
    return float(
        np.average(
            [math.erfc(window / (math.sqrt(2) * sigma)) for window, _ in windows],
            weights=[weight for _, weight in windows],
        )
    )


def _accuracy_score(value: float | None, expected: float, theta: float) -> float | None:
    if value is None or not math.isfinite(value) or not math.isfinite(expected) or expected <= 0:
        return None
    low_blend = min(1.0, max(0.0, ACCURACY_TRANSITION_STARS - theta))
    points = POINTS["accuracy"] + 5 * low_blend
    return round(float(np.clip(50 - points * math.log2(max(value, 1e-6) / expected), 0, 100)), 1)


# what each skill is measured on, the unit of that measure, and the maps that test it
_TESTS = {
    "aim": ("the cursor speed of your hardest jumps", "{:.1f} circle widths/s", "jumps", "bigger or faster jumps"),
    "flow_aim": (
        "the cursor speed of your fastest spaced streams",
        "{:.1f} circle widths/s",
        "spaced streams",
        "wider or faster spaced streams",
    ),
    "speed": ("your fastest bursts and streams", "{:.0f} BPM", "bursts or streams", "faster bursts and streams"),
    "sliders": ("the difficulty of your hardest sliders", "{:.1f}", "sliders", "long, fast or curvy sliders"),
    "reading": ("", "", "", ""),  # never untested; too few maps: see _needs
}


def _needs(skill: str, maps: int, untested: bool, tested: float, expected: float) -> str:
    """What to play to get a score for ``skill``: harder maps when everything played was easier than expected and
    nearly all of it was held, else more maps."""
    what, unit, noun, harder = _TESTS[skill]
    if untested:
        return (
            f"You held almost everything you played, but {what} so far ({unit.format(tested)}) is below what your "
            f"comfort level expects ({unit.format(expected)}): play maps with {harder} to find your limit."
        )
    more = max(1, MIN_MAPS - maps)
    maps_text = f"{more} more different map{'s' if more > 1 else ''}"
    if skill == "reading":
        return f"Pass {maps_text} to get a score."
    return f"Play {maps_text} with {noun} to get a score."


def _aggregate(rows: list[dict]) -> tuple[float | None, list[dict]]:
    best: dict[str, dict] = {}
    for row in rows:
        value = row.get("value")
        if value is None or not math.isfinite(value):
            continue
        key = str(row["map"])
        if key not in best or value > best[key]["value"]:
            best[key] = row
    chosen = sorted(best.values(), key=lambda row: row["value"], reverse=True)
    weights = np.power(RANK_DECAY, np.arange(len(chosen)))
    return (float(np.average([r["value"] for r in chosen], weights=weights)) if chosen else None, chosen)


def ratings(objects: pd.DataFrame, metas: pd.DataFrame, theta: float | None) -> dict[str, dict]:
    """Eight Lab-style ratings from the existing Coach analysis tables."""
    result = {skill: {"score": None, "maps": 0, "reason": "Comfort not established"} for skill in POINTS}
    result["consistency"] = star_consistency(metas, theta, comfort=True)
    if theta is None or not math.isfinite(theta) or objects.empty:
        return result
    O = objects.copy()
    # Lab treats each map/mod combination as a separate demonstrated configuration.
    unique_metas = metas.drop_duplicates("key", keep="last").set_index("key")
    mods = unique_metas["mods"].astype(str)
    O["map_md5"] = O["map_md5"].astype(str) + ":" + O["replay_key"].map(mods).fillna("unknown")
    weights = replay_weight(metas["stars"].to_numpy(float), theta)
    O["w"] = O["replay_key"].map(dict(zip(metas["key"], weights))).fillna(1.0)
    P = played_notes(O)
    raw: dict[str, list[dict]] = {skill: [] for skill in POINTS}
    for skill, values, mask, top in (
        ("aim", aim_values(P), P["pattern"].isin(["jump", "spaced"]), 30),
        ("flow_aim", flow_values(P), P["spaced_stream"].astype(bool) & (P["run_pos"] > 0), 50),
    ):
        for row in values.to_dict("records"):
            selected = P[mask & (P["replay_key"] == row["replay_key"])].copy()
            selected["move_speed"] = selected["velocity_real"] * 1000 / (2 * selected["radius"])
            share = float(selected.nlargest(top, "move_speed")["head_hit"].astype(bool).mean())
            demand = row["intensity"] if skill == "aim" else row["speed"] * row["amount"]
            raw[skill].append({**row, "value": demand * share**0.8, "exposure": demand, "success_share": share})
    for row in speed_values(P).to_dict("records"):
        raw["speed"].append(
            {
                **row,
                "value": row["bpm"],
                "exposure": float(
                    P.loc[(P["replay_key"] == row["replay_key"]) & (P["run_len"] >= 3), "stream_bpm"].max()
                ),
                "success_share": row["clean"] / max(1, row["runs"]),
            }
        )
    S = P[(P["kind"] == "slider") & P["head_hit"].astype(bool)].copy()
    if not S.empty:
        S["difficulty"] = slider_difficulty(S)
        S["map"] = _map_key(S)
        for (_, map_key), sliders in S.groupby(["replay_key", "map"], sort=False):
            if len(sliders) < 10:
                continue
            selected = sliders.nlargest(30, "difficulty")
            demand = float(selected["difficulty"].mean())
            share = float((~selected["broke"].fillna(False).astype(bool)).mean())
            raw["sliders"].append(
                {"map": map_key, "value": demand * share**3, "exposure": demand, "success_share": share}
            )
    for row in reading_values(P).to_dict("records"):
        raw["reading"].append(
            {**row, "exposure": row["ar_factor"] * row["bpm_factor"], "success_share": row["accuracy"]}
        )
    for skill in ("aim", "flow_aim", "speed", "sliders", "reading"):
        value, chosen = _aggregate(raw[skill])
        expected = _expected(skill, theta)
        exposure = max((row["exposure"] for row in chosen if math.isfinite(row["exposure"])), default=0.0)
        share = float(np.mean([row["success_share"] for row in chosen])) if chosen else None
        untested = bool(chosen and skill != "reading" and exposure < expected and share >= 0.95)
        score = _score(skill, value, expected) if len(chosen) >= MIN_MAPS and not untested else None
        result[skill] = {
            "score": score,
            "maps": len(chosen),
            "measured": value,
            "expected": expected,
            "tested_demand": exposure,
            "success_share": share,
            # held ~everything played, all of it easier than expected: the skill is at least as good as that
            "at_least": _score(skill, exposure, expected) if untested else None,
            "needs": None if score is not None else _needs(skill, len(chosen), untested, exposure, expected),
            "reason": "Insufficient challenge"
            if untested
            else f"Need {MIN_MAPS} relevant map/mod configurations"
            if len(chosen) < MIN_MAPS
            else "Best per map/mod configuration; 0.95 rank decay",
        }
    duration_rows = tempo_curve(P)
    demand_objects = P.copy()
    demand_objects["head_hit"] = True
    demands = tempo_curve(demand_objects)
    exposure_lookup = {(r["replay_key"], r["window"]): r["bpm"] for r in demands.to_dict("records")}
    parts = []
    duration_parts = []
    for duration in STAMINA_SHARES:
        rows = [
            {**row, "value": row["bpm"], "exposure": exposure_lookup.get((row["replay_key"], duration), 0.0)}
            for row in duration_rows.to_dict("records")
            if row["window"] == duration
        ]
        value, chosen = _aggregate(rows)
        if value is None:
            continue
        expected = _expected("stamina", theta, duration=duration)
        exposure = max((r["bpm"] for r in demands.to_dict("records") if r["window"] == duration), default=0.0)
        share = float(np.mean([r["value"] / max(r["exposure"], 1e-6) for r in chosen]))
        untested = exposure < expected and share >= 0.95
        usable = len(chosen) >= MIN_MAPS and not untested
        duration_parts.append(
            {
                "duration": duration,
                "measured": value,
                "maps": len(chosen),
                "tested_demand": exposure,
                "success_share": share,
                "expected": expected,
                "untested": untested,
            }
        )
        if usable:
            parts.append(_score("stamina", value, expected))
    # no duration scored, but some only because nothing was demanding enough: a lower bound, and what to play
    open_parts = [d for d in duration_parts if d["untested"]]
    at_least = (
        round(float(np.mean([_score("stamina", d["tested_demand"], d["expected"]) for d in open_parts])), 1)
        if open_parts and not parts
        else None
    )
    stamina_needs = None
    if not parts:
        first = open_parts[0] if open_parts else None
        stamina_needs = (
            f"You kept up with almost every stretch you played, but your densest {first['duration']}-second stretch so "
            f"far ({first['tested_demand']:.0f} BPM of 1/4 notes) is below what your comfort level expects "
            f"({first['expected']:.0f} BPM): play maps with longer streams or dense 1/4 sections."
            if first
            else f"Play {MIN_MAPS} different maps with streams or dense 1/4 sections of at least 10 seconds."
        )
    result["stamina"] = {
        "score": round(float(np.mean(parts)), 1) if parts else None,
        "maps": int(duration_rows["map"].nunique()) if not duration_rows.empty else 0,
        "parts": duration_parts,
        "at_least": at_least,
        "needs": stamina_needs,
        "reason": "Mean of measured duration scores; easy or untested durations stay unknown",
    }
    singles = P[(P["run_len"] < 3) & P["head_hit"].astype(bool)]
    if len(singles):
        w = singles["w"].astype(float)
        error = float(np.average(singles["head_result"] != 300, weights=w))
        od = singles["replay_key"].map(unique_metas["od"]).astype(float)
        window = np.maximum(0.0, 79.5 - 6 * od.to_numpy())
        window_weights = (
            pd.DataFrame({"window": window, "weight": w.to_numpy()}).groupby("window", sort=True)["weight"].sum()
        )
        windows = [(float(hit_window), float(weight)) for hit_window, weight in window_weights.items()]
        expected = _accuracy_expected(windows, theta) if windows else math.nan
        result["accuracy"] = {
            "score": _accuracy_score(error, expected, theta) if len(singles) >= 60 else None,
            "maps": int(singles["map_md5"].nunique()),
            "hit_single_notes": len(singles),
            "measured": error,
            "expected": expected,
            "expected_top": _accuracy_expected(windows, 10.0) if windows else math.nan,
            "od_windows": windows,
            "reason": "Effective-OD-matched non-300 share on hit single heads",
        }
    return result


def at_level(rows: dict[str, dict], theta: float) -> dict[str, float | None]:
    """Rebase measured abilities to another star reference without rereading replays."""
    out: dict[str, float | None] = {}
    for skill, row in rows.items():
        if skill == "stamina":
            scores = []
            for part in row.get("parts", []):
                expected = _expected(skill, theta, duration=part["duration"])
                if part["maps"] >= MIN_MAPS and not (
                    part["tested_demand"] < expected and part["success_share"] >= 0.95
                ):
                    scores.append(_score(skill, part["measured"], expected))
            out[skill] = round(float(np.mean(scores)), 1) if scores else None
        elif skill == "accuracy":
            windows = row.get("od_windows")
            out[skill] = (
                _accuracy_score(row.get("measured"), _accuracy_expected(windows, theta), theta)
                if row.get("score") is not None and windows
                else row.get("score")
            )
        elif skill in ("reading", "consistency"):
            out[skill] = row.get("score")
        elif row.get("maps", 0) < MIN_MAPS:
            out[skill] = None
        else:
            expected = _expected(skill, theta)
            untested = row.get("tested_demand", 0) < expected and (row.get("success_share") or 0) >= 0.95
            out[skill] = None if untested else _score(skill, row.get("measured"), expected)
    return out
