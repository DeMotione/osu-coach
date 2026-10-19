"""Experimental NoMod skillset recommendation over the existing Coach pool.

Pool ``s_*`` values describe training relevance. Demands are a separate,
unvalidated projection from pool features, relative to the player's comfort stars.
"""

from __future__ import annotations

import math
import re
import statistics

import pandas as pd

from osu_coach.analysis.skill_scale import SPEED_POINTS, expected_speed_bpm, speed_bpm_for_rating, speed_rating
from osu_coach.maps.domain import SKILLS, map_url, why

FEATURE_POINTS = {
    "aim": 12,
    "flow_aim": 12,
    "stamina": 15,
    "accuracy": 15,
    "sliders": 12,
    "reading": 12,
    "consistency": 12,
}
GOALS = {
    "Warm-up": (-0.5, -15.0, -10.0),
    "Comfort": (0.0, -5.0, 0.0),
    "Push": (0.3, 5.0, 0.0),
}
STAR_WINDOW = 0.2
STAR_SCALE = 0.2
SKILL_SCALE = 20.0
RISK_WEIGHT = 1.0
HISTORY_WEIGHT = 0.5
SPEED_MIN_TEMPO_RATIO = 0.8


def _number(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _get(row: dict, key: str, default: float = 0.0) -> float:
    value = _number(row.get(key))
    return value if value is not None else default


def _speed_bpm(row: dict) -> float | None:
    """Use the third run in rebuilt pools; old pools only store stream/burst medians."""
    if "speed_runs" in row:
        return _number(row.get("speed_bpm")) if _get(row, "speed_runs") >= 3 else None
    bpm = max(_get(row, "stream_bpm"), _get(row, "burst_bpm"))
    return bpm if bpm > 0 else None


def _features(row: dict) -> dict[str, float]:
    """The Lab's coarse pool feature composites, in Coach skill names."""
    radius = max(1.0, 54.4 - 4.48 * _get(row, "cs", 4))
    bpm = max(_get(row, "stream_bpm"), _get(row, "burst_bpm"))
    speed_bpm = _speed_bpm(row)
    odd = _get(row, "odd_rhythm_share")
    density = _get(row, "density_p90")
    ar = _get(row, "ar", 9)
    values = {
        "aim": _get(row, "jump_velocity") * 1000 / (2 * radius) * (1 + 0.3 * _get(row, "sharp_share")),
        "flow_aim": _get(row, "aim") * math.sqrt(max(0, _get(row, "spaced_stream_share"))) * bpm / 180,
        "speed": speed_bpm or 0.0,
        "stamina": bpm
        * math.log1p(max(0, _get(row, "stream_notes")))
        / math.log(401)
        * math.sqrt(max(0, _get(row, "max_run")) / 32)
        * (max(0, _get(row, "drain_length")) / 120) ** 0.25,
        "accuracy": 20 / max(1, 80 - 6 * _get(row, "od", 8)) * (1 + 2 * odd) * (1 + 0.03 * density),
        "sliders": _get(row, "slider_velocity")
        * 1000
        / (2 * radius)
        * (1 + _get(row, "reverse_share"))
        * (1 + 10 * max(0, 1 - _get(row, "slider_factor", 1))),
        "reading": density * (1 + odd) * (1 + max(0, 8 - ar) / 4 + max(0, ar - 10) / 2),
        "consistency": math.sqrt(max(0, _get(row, "drain_length")) / 120)
        * (0.5 + 0.5 * max(0, min(1, _get(row, "evenness", 1)))),
    }
    required = {
        "aim": ("cs", "jump_velocity", "sharp_share"),
        "flow_aim": ("aim", "spaced_stream_share"),
        "stamina": ("stream_notes", "max_run", "drain_length"),
        "accuracy": ("od", "odd_rhythm_share", "density_p90"),
        "sliders": ("cs", "slider_velocity", "reverse_share", "slider_factor"),
        "reading": ("density_p90", "odd_rhythm_share", "ar"),
        "consistency": ("drain_length", "evenness"),
    }
    result = {}
    for skill, value in values.items():
        needs_bpm = skill in ("flow_aim", "stamina")
        if needs_bpm and _number(row.get("stream_bpm")) is None and _number(row.get("burst_bpm")) is None:
            continue
        if any(_number(row.get(key)) is None for key in required.get(skill, ())):
            continue
        if math.isfinite(value) and value > 0:
            result[skill] = value
    return result


def _candidates(pool: pd.DataFrame, theta: float, assessed: tuple[str, ...]) -> tuple[list[dict], dict[str, int]]:
    records = pool.to_dict("records")
    valid = []
    seen = set()
    rejected: dict[str, int] = {}
    for row in records:
        stars = _number(row.get("stars"))
        md5 = row.get("md5")
        valid_id = isinstance(md5, str) and re.fullmatch(r"[0-9a-f]{32}", md5)
        if stars is None or stars <= 0 or not valid_id or md5 in seen:
            reason = (
                "Missing map star difficulty or ID"
                if stars is None or stars <= 0 or not valid_id
                else "Duplicate map configuration"
            )
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        seen.add(md5)
        valid.append((row, _features(row)))
    refs = {}
    for skill in assessed:
        if skill == "speed":
            continue
        items = sorted(
            ((row, features[skill]) for row, features in valid if skill in features),
            key=lambda pair: (abs(pair[0]["stars"] - theta), str(pair[0]["md5"])),
        )
        near = [pair for pair in items if abs(pair[0]["stars"] - theta) <= 0.5]
        chosen = (near if len(near) >= 30 else items)[:200]
        if chosen:
            refs[skill] = statistics.median(value for _, value in chosen)
    result = []
    for row, features in valid:
        demands = {}
        relevance = {}
        projection = {}
        for skill in assessed:
            value = features.get(skill)
            ref = refs.get(skill)
            affinity = _number(row.get("s_" + skill))
            if value is None or affinity is None or not 0 <= affinity <= 1 or (skill != "speed" and ref is None):
                continue
            if skill == "speed":
                demands[skill] = speed_rating(value, theta)
                projection[skill] = {
                    "raw_feature": value,
                    "reference_bpm": expected_speed_bpm(theta),
                    "points_per_doubling": SPEED_POINTS,
                    "source": "third_fastest_run" if "speed_runs" in row else "legacy_pool_bpm_proxy",
                }
                relevance[skill] = affinity
                continue
            demands[skill] = 50 + 20 * (row["stars"] - theta) + FEATURE_POINTS[skill] * math.log2(value / ref)
            relevance[skill] = affinity
            projection[skill] = {
                "raw_feature": value,
                "reference_median": ref,
                "star_points": 20,
                "feature_points": FEATURE_POINTS[skill],
            }
        result.append({"row": row, "demands": demands, "relevance": relevance, "projection": projection})
    return result, rejected


def recommend(
    pool: pd.DataFrame,
    theta: float,
    abilities: dict[str, float],
    skill: str,
    assessed: tuple[str, ...],
    kappa: float = 0.5,
    min_relevance: float = 0.3,
    played: frozenset[str] = frozenset(),
    targets=None,
) -> dict:
    """Return every eligible map for each goal, plus explicit exclusion counts."""
    if not math.isfinite(theta) or theta <= 0 or skill not in SKILLS:
        raise ValueError("A positive comfort rating and known target skill are required.")
    if not math.isfinite(kappa) or kappa < 0 or not math.isfinite(min_relevance) or not 0 <= min_relevance <= 1:
        raise ValueError("Invalid skill adjustment or relevance threshold.")
    if not assessed or len(set(assessed)) != len(assessed) or skill not in assessed or set(assessed) - set(SKILLS):
        raise ValueError("Assessed skills must be distinct and include the target skill.")
    for key, value in abilities.items():
        if key not in SKILLS or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError(f"Invalid player rating: {key}.")
    low_accuracy = skill == "accuracy" and theta < 5.5
    od_min = min(8.5, 3.0 + theta) if low_accuracy else None
    adjusted = theta + kappa * (abilities[skill] - 50) / 50 if skill in abilities else None
    if low_accuracy and adjusted is not None:
        adjusted = max(1.5, adjusted)  # Keep the warm-up target positive for new players.
    candidates, rejected = _candidates(pool, theta, assessed)
    result = {}
    for goal, (star_offset, skill_offset, margin) in GOALS.items():
        target = adjusted + star_offset if adjusted is not None else None
        target_speed_bpm = (
            speed_bpm_for_rating(abilities[skill] + skill_offset, theta)
            if skill == "speed" and skill in abilities
            else None
        )
        if target is not None and target <= 0:
            raise ValueError("The adjusted target stars must be positive.")
        star_window = STAR_WINDOW
        if low_accuracy and target is not None:
            # Widen only when the narrower window has no usable timing map.
            for width in (STAR_WINDOW, 0.5, 1.0):
                star_window = width
                if any(
                    candidate["row"]["md5"] not in played
                    and _number(candidate["row"].get("od")) is not None
                    and candidate["row"]["od"] >= od_min
                    and abs(candidate["row"]["stars"] - target) <= width + 1e-12
                    and skill in candidate["demands"]
                    and candidate["relevance"].get(skill, -1) >= min_relevance
                    and all(other in abilities and other in candidate["demands"] for other in assessed)
                    for candidate in candidates
                ):
                    break
        star_scale = STAR_SCALE * star_window / STAR_WINDOW  # a window widened for timing maps is scored as wide
        excluded: dict[str, int] = dict(rejected)
        eligible = []
        for candidate in candidates:
            row, demands, relevance = candidate["row"], candidate["demands"], candidate["relevance"]
            stars, md5 = row["stars"], str(row["md5"])
            reason = None
            if md5 in played:
                reason = "Already played"
            elif skill not in abilities:
                reason = "Target player rating unknown"
            elif any(other not in abilities for other in assessed):
                reason = "Assessed player rating unknown"
            elif low_accuracy and (_number(row.get("od")) is None or row["od"] < od_min):
                reason = f"Timing OD below {od_min:g}"
            elif target is None or abs(stars - target) > star_window + 1e-12:
                reason = "Outside star window"
            elif skill not in demands or skill not in relevance:
                reason = "Target demand or relevance unknown"
            elif relevance[skill] < min_relevance:
                reason = "Insufficient target relevance"
            elif target_speed_bpm is not None and _speed_bpm(row) < SPEED_MIN_TEMPO_RATIO * target_speed_bpm:
                reason = "Tapping tempo too far below target"
            elif any(other not in demands for other in assessed):
                reason = "Assessed map demand unknown"
            if reason:
                excluded[reason] = excluded.get(reason, 0) + 1
                continue
            eligible.append(candidate)
        # Demands rise 20 points a star, abilities don't move the target stars that far: a rating far from 50 asks
        # for demands no map at the target stars has. Measured from the nearest demand they do have, the best map
        # available scores near 0 instead of every map scoring far below it (#33).
        reach = {
            k: (min(c["demands"][k] for c in eligible), max(c["demands"][k] for c in eligible))
            for k in (assessed if eligible else ())
        }
        wanted = abilities[skill] + skill_offset if skill in abilities else None
        reachable = min(max(wanted, reach[skill][0]), reach[skill][1]) if reach and wanted is not None else None
        ranked = []
        for candidate in eligible:
            row, demands, relevance = candidate["row"], candidate["demands"], candidate["relevance"]
            stars, md5 = row["stars"], str(row["md5"])
            star_term = -(((stars - target) / star_scale) ** 2)
            skill_term = -(((demands[skill] - reachable) / SKILL_SCALE) ** 2)
            bottlenecks = []
            for other in assessed:
                if other == skill:
                    continue
                # only the overload beyond what every map here asks of that skill
                floor = max(abilities[other] + margin, reach[other][0])
                overload = max(0.0, demands[other] - floor)
                bottlenecks.append(
                    {
                        "skill": other,
                        "demand": demands[other],
                        "ability": abilities[other],
                        "margin": margin,
                        "least_demand": reach[other][0],
                        "overload": overload,
                        "sigma": 20.0,
                        "importance": 1.0,
                        "risk": (overload / 20.0) ** 2,
                    }
                )
            risk = sum(part["risk"] for part in bottlenecks)
            terms = {
                "stars": star_term,
                "skill": skill_term,
                "bottlenecks": -RISK_WEIGHT * risk,
                "history": HISTORY_WEIGHT * (1 - 1),
            }
            ranked.append(
                {
                    **row,
                    "skill": skill,
                    "url": map_url(row),
                    "why": why(row, skill, targets) if targets is not None else "",
                    "skill_demand": demands[skill],
                    "relevance": relevance[skill],
                    "formula_score": sum(terms.values()),
                    "breakdown": {
                        "id": md5 + "@NM",
                        "mods": "NM",
                        "terms": terms,
                        "risk": risk,
                        "bottlenecks": bottlenecks,
                        "demands": demands,
                        "abilities": {k: abilities[k] for k in assessed},
                        "demand_projection": candidate["projection"],
                        "target_stars": target,
<<<<<<< HEAD
                        "target_demand": wanted,
                        "reachable_demand": reachable,
=======
                        "target_demand": abilities[skill] + skill_offset,
                        "target_speed_bpm": target_speed_bpm,
                        "minimum_speed_bpm": SPEED_MIN_TEMPO_RATIO * target_speed_bpm if target_speed_bpm else None,
>>>>>>> origin/main
                        "kappa_s": kappa,
                        "star_window": star_window,
                        "star_scale": star_scale,
                        "skill_scale": SKILL_SCALE,
                        "other_margin": margin,
                        "risk_weight": RISK_WEIGHT,
                        "history_weight": HISTORY_WEIGHT,
                        "history": 1,
                        "history_source": "Neutral assumption",
                        "experimental_demands": True,
                    },
                }
            )
        ranked.sort(key=lambda row: (-row["formula_score"], str(row["md5"]) + "@NM"))
        if low_accuracy and not ranked and target is not None and all(other in abilities for other in assessed):
            excluded["No qualified timing map within 1★ of target"] = 1
        result[goal] = {
            "target_stars": target,
            "target_demand": wanted,
            "star_min": target - star_window if target is not None else None,
            "star_max": target + star_window if target is not None else None,
            "eligible": len(ranked),
            "excluded": excluded,
            "maps": ranked,
        }
    return {"skill_adjusted_stars": adjusted, "goals": result, "candidate_count": len(candidates), "experimental": True}
