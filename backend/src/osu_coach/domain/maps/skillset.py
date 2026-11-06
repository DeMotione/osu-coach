"""NoMod map recommendation for one skill from the bundled pool.

Pool ``s_*`` values describe training relevance. Demands are a separate,
unvalidated projection from pool features, relative to the player's comfort stars.
"""

from __future__ import annotations

import math
import re
import statistics
from bisect import bisect_left
from collections.abc import Mapping, Sequence
from typing import Any

from osu_coach.domain.maps.suggestions import SKILLS, map_url
from osu_coach.domain.numeric.values import finite_or_none
from osu_coach.domain.player import algorithm as alg
from osu_coach.domain.player.skill_scale import SPEED_POINTS, expected_speed_bpm, speed_bpm_for_rating, speed_rating
from osu_coach.domain.replays.configuration import Configuration

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


def _get(row: dict, key: str, default: float = 0.0) -> float:
    value = finite_or_none(row.get(key))
    return value if value is not None else default


def _speed_bpm(row: dict) -> float | None:
    """Use the third run in rebuilt pools; old pools only store stream/burst medians."""
    if "speed_runs" in row:
        return finite_or_none(row.get("speed_bpm")) if _get(row, "speed_runs") >= 3 else None
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
        "flow_aim": (
            _get(row, "flow_velocity") * 1000 / (2 * radius)
            if finite_or_none(row.get("flow_velocity")) is not None
            else _get(row, "aim") * bpm / 180
        )
        * math.sqrt(max(0, _get(row, "spaced_stream_share")))
        * (1 + 0.3 * _get(row, "flow_turn_share")),
        "speed": speed_bpm or 0.0,
        "stamina": bpm
        * math.log1p(max(0, _get(row, "stream_notes")))
        / math.log(401)
        * math.sqrt(max(0, _get(row, "max_run")) / 32)
        * (max(0, _get(row, "drain_length")) / 120) ** 0.15
        * (max(0.1, _get(row, "run_duration_p90", 10)) / 10) ** 0.25
        * (1 + 0.15 / (1 + max(0, _get(row, "run_rest_median", 2)))),
        "accuracy": 20
        * (
            0.7 / max(1, _get(row, "hit300_ms", 80 - 6 * _get(row, "od", 8)))
            + 0.4 / max(1, _get(row, "hit100_ms", 140 - 8 * _get(row, "od", 8)))
            + 0.3 / max(1, _get(row, "hit50_ms", 200 - 10 * _get(row, "od", 8)))
        )
        * (1 + 2 * odd)
        * (1 + 0.03 * density),
        "sliders": _get(row, "slider_velocity")
        * 1000
        / (2 * radius)
        * (1 + _get(row, "reverse_share"))
        * (1 + 10 * max(0, 1 - _get(row, "slider_factor", 1)))
        * (1 + 0.02 * _get(row, "slider_length_norm") + 0.03 * _get(row, "slider_turn"))
        * (1 + 0.1 / max(0.1, _get(row, "slider_transition", 1000) / 1000)),
        "reading": density * (1 + odd)
        + alg.READ_LOW_WEIGHT * max(0, alg.READ_LOW_AR - ar) ** 2
        + alg.READ_FAST_WEIGHT * max(0, ar - alg.READ_FAST_AR) ** 2
        + (1 if "HD" in str(row.get("mods") or "") else 0)
        * (
            alg.READ_HD_BASE
            + alg.READ_HD_LOW_WEIGHT * max(0, alg.READ_LOW_AR - ar) ** 2
            + alg.READ_HD_HIGH_WEIGHT * max(0, ar - alg.READ_HD_UPPER_AR) ** 2
        )
        * (1 + alg.READ_HD_DENSITY_WEIGHT * density),
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
        if needs_bpm and finite_or_none(row.get("stream_bpm")) is None and finite_or_none(row.get("burst_bpm")) is None:
            continue
        if any(finite_or_none(row.get(key)) is None for key in required.get(skill, ())):
            continue
        if math.isfinite(value) and value > 0:
            result[skill] = value
    return result


def _check(
    theta: float,
    abilities: Mapping[str, float],
    skill: str,
    assessed: tuple[str, ...],
    kappa: float,
    min_relevance: float,
) -> None:
    """The inputs both recommenders need: a positive comfort level, known skills and ratings, sane settings."""
    if not math.isfinite(theta) or theta <= 0 or skill not in SKILLS:
        raise ValueError("A positive comfort rating and known target skill are required.")
    if not math.isfinite(kappa) or kappa < 0 or not math.isfinite(min_relevance) or not 0 <= min_relevance <= 1:
        raise ValueError("Invalid skill adjustment or relevance threshold.")
    if not assessed or len(set(assessed)) != len(assessed) or skill not in assessed or set(assessed) - set(SKILLS):
        raise ValueError("Assessed skills must be distinct and include the target skill.")
    for key, value in abilities.items():
        if key not in SKILLS or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError(f"Invalid player rating: {key}.")


def _adjusted_stars(theta: float, kappa: float, abilities: Mapping[str, float], skill: str) -> float | None:
    """The comfort level moved by how far the skill's rating is from typical (None: the skill has no rating)."""
    return theta + kappa * (abilities[skill] - 50) / 50 if skill in abilities else None


def _demand(skill: str, value: float, stars: float, theta: float, reference: float | None) -> float:
    """What a map asks of the skill on the rating scale: 20 points a star from the comfort level, plus the feature
    against typical maps (``reference``); speed straight from its tapping tempo."""
    if skill == "speed":
        return speed_rating(value, theta)
    return 50 + 20 * (stars - theta) + FEATURE_POINTS[skill] * math.log2(value / reference)


def _bottlenecks(
    skill: str, assessed: tuple[str, ...], demands: Mapping[str, float], abilities: Mapping[str, float], margin: float
) -> list[dict]:
    """The other skills' overload: only what a map asks beyond the player's rating plus the goal's margin."""
    out = []
    for other in assessed:
        if other == skill:
            continue
        overload = max(0.0, demands[other] - (abilities[other] + margin))
        out.append(
            {
                "skill": other,
                "demand": demands[other],
                "ability": abilities[other],
                "margin": margin,
                "overload": overload,
                "sigma": 20.0,
                "importance": 1.0,
                "risk": (overload / 20.0) ** 2,
            }
        )
    return out


def _candidates(
    pool: Sequence[Mapping[str, Any]], theta: float, assessed: tuple[str, ...]
) -> tuple[list[dict], dict[str, int]]:
    records = list(pool)
    valid = []
    seen = set()
    rejected: dict[str, int] = {}
    for row in records:
        stars = finite_or_none(row.get("stars"))
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
            affinity = finite_or_none(row.get("s_" + skill))
            if value is None or affinity is None or not 0 <= affinity <= 1 or (skill != "speed" and ref is None):
                continue
            demands[skill] = _demand(skill, value, row["stars"], theta, ref)
            if skill == "speed":
                projection[skill] = {
                    "raw_feature": value,
                    "reference_bpm": expected_speed_bpm(theta),
                    "points_per_doubling": SPEED_POINTS,
                    "source": "third_fastest_run" if "speed_runs" in row else "legacy_pool_bpm_proxy",
                }
                relevance[skill] = affinity
                continue
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
    pool: Sequence[Mapping[str, Any]],  # the pool's map rows
    theta: float,
    abilities: dict[str, float],
    skill: str,
    assessed: tuple[str, ...],
    kappa: float = 0.5,
    min_relevance: float = 0.3,
    played: frozenset[str] = frozenset(),
) -> dict:
    """Return every eligible map for each goal, plus explicit exclusion counts."""
    _check(theta, abilities, skill, assessed, kappa, min_relevance)
    low_accuracy = skill == "accuracy" and theta < 5.5
    od_min = min(8.5, 3.0 + theta) if low_accuracy else None
    adjusted = _adjusted_stars(theta, kappa, abilities, skill)
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
        star_scale = STAR_SCALE
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
            elif low_accuracy and (finite_or_none(row.get("od")) is None or row["od"] < od_min):
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
        wanted = abilities[skill] + skill_offset if skill in abilities else None
        reachable = wanted
        ranked = []
        for candidate in eligible:
            row, demands, relevance = candidate["row"], candidate["demands"], candidate["relevance"]
            stars, md5 = row["stars"], str(row["md5"])
            star_term = -(((stars - target) / star_scale) ** 2)
            skill_term = -(((demands[skill] - reachable) / SKILL_SCALE) ** 2)
            bottlenecks = [
                {**b, "least_demand": None} for b in _bottlenecks(skill, assessed, demands, abilities, margin)
            ]
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
                    "configuration_id": Configuration(md5).key,
                    "mods": "NM",
                    "rate": 1.0,
                    "skill": skill,
                    "url": map_url(row),
                    "skill_demand": demands[skill],
                    "relevance": relevance[skill],
                    "formula_score": sum(terms.values()),
                    "breakdown": {
                        "id": Configuration(md5).key,
                        "mods": "NM",
                        "terms": terms,
                        "risk": risk,
                        "bottlenecks": bottlenecks,
                        "demands": demands,
                        "abilities": {k: abilities[k] for k in assessed},
                        "demand_projection": candidate["projection"],
                        "target_stars": target,
                        "target_demand": wanted,
                        "reachable_demand": reachable,
                        "target_speed_bpm": target_speed_bpm,
                        "minimum_speed_bpm": SPEED_MIN_TEMPO_RATIO * target_speed_bpm if target_speed_bpm else None,
                        "kappa_s": kappa,
                        "star_window": star_window,
                        "star_scale": star_scale,
                        "skill_scale": SKILL_SCALE,
                        "other_margin": margin,
                        "risk_weight": RISK_WEIGHT,
                        "history_weight": HISTORY_WEIGHT,
                        "history": 1,
                        "history_source": "Neutral assumption",
                    },
                }
            )
        ranked.sort(key=lambda row: (-row["formula_score"], str(row["md5"]) + "@NM"))
        if low_accuracy and not ranked and target is not None and all(other in abilities for other in assessed):
            excluded["No qualified timing map in the configured star window"] = 1
        result[goal] = {
            "target_stars": target,
            "target_demand": wanted,
            "star_min": target - star_window if target is not None else None,
            "star_max": target + star_window if target is not None else None,
            "eligible": len(ranked),
            "excluded": excluded,
            "maps": ranked,
        }
    return {"skill_adjusted_stars": adjusted, "goals": result, "candidate_count": len(candidates)}


def recommend_modified(
    base_pool: Sequence[Mapping[str, Any]],
    variants,
    theta: float,
    abilities: dict[str, float],
    skill: str,
    assessed: tuple[str, ...],
    kappa: float,
    min_relevance: float,
    played: frozenset[str],
    history: dict[str, float],
    limit: int = 100,
) -> dict:
    """Stream exact variants through all goals, retaining their highest F values.

    `limit` bounds the serialized job result; the best candidate still comes from
    the complete set of available configurations, never from a coarse shortlist.
    """
    _check(theta, abilities, skill, assessed, kappa, min_relevance)
    # The mechanical-feature term is a residual relative to typical maps at the
    # *candidate's* modified stars. The 20-point star term supplies the overall
    # challenge, so a speed/precision effect captured by stars is not counted
    # again as a raw feature increase against a fixed comfort-star reference.
    samples = [
        (float(r["stars"]), _features(r))
        for r in base_pool
        if finite_or_none(r.get("stars")) is not None and float(r["stars"]) > 0
    ]
    grid = [1.0 + i * 0.25 for i in range(57)]
    references: dict[str, list[float | None]] = {}
    for key in assessed:
        if key == "speed":
            continue
        values = []
        for point in grid:
            near = [features[key] for stars, features in samples if abs(stars - point) <= 0.5 and key in features]
            values.append(statistics.median(near) if len(near) >= 10 else None)
        references[key] = values

    def reference(key: str, stars: float) -> float | None:
        values = references.get(key)
        if not values:
            return None
        pos = bisect_left(grid, stars)
        before = next(
            ((grid[i], values[i]) for i in range(min(pos, len(grid) - 1), -1, -1) if values[i] is not None), None
        )
        after = next(((grid[i], values[i]) for i in range(pos, len(grid)) if values[i] is not None), None)
        if before and after and before[0] != after[0]:
            return before[1] + (after[1] - before[1]) * (stars - before[0]) / (after[0] - before[0])
        return before[1] if before else after[1] if after else None

    missing = tuple(key for key in assessed if key not in abilities)
    adjusted = _adjusted_stars(theta, kappa, abilities, skill)
    goals = {}
    for goal, (star_offset, skill_offset, margin) in GOALS.items():
        target = adjusted + star_offset if adjusted is not None else None
        if target is not None and target <= 0:
            raise ValueError("The adjusted target stars must be positive.")
        goals[goal] = {
            "target_stars": target,
            "target_demand": abilities[skill] + skill_offset if skill in abilities else None,
            "star_min": target - STAR_WINDOW if target is not None else None,
            "star_max": target + STAR_WINDOW if target is not None else None,
            "eligible": 0,
            "excluded": {},
            "maps": [],
            "margin": margin,
        }
    if missing:
        reason = "Target player rating unknown" if skill in missing else "Assessed player rating unknown"
        for data in goals.values():
            data["excluded"][reason] = 1
            del data["margin"]
        return {"skill_adjusted_stars": adjusted, "goals": goals, "candidate_count": 0, "result_limit": limit}
    count = 0
    best: dict[str, dict[str, dict]] = {goal: {} for goal in goals}
    for row in variants:
        count += 1
        md5 = str(row.get("md5") or "")
        config_id = str(row.get("configuration_id") or "")
        stars = finite_or_none(row.get("stars"))
        feature = _features(row)
        demands = {}
        projections = {}
        for key in assessed:
            value = feature.get(key)
            ref = reference(key, stars) if key != "speed" and stars is not None else None
            if value is None or (key != "speed" and (ref is None or ref <= 0)) or stars is None:
                continue
            demands[key] = _demand(key, value, stars, theta, ref)
            projections[key] = {
                "raw_feature": value,
                "reference_median": ref,
                "star_points": 20,
                "feature_points": FEATURE_POINTS.get(key),
            }
        for goal, data in goals.items():
            target = data["target_stars"]
            target_bpm = speed_bpm_for_rating(data["target_demand"], theta) if skill == "speed" else None
            relevance = finite_or_none(row.get("s_" + skill))
            reason = None
            if md5 in played:
                reason = "Already played"
            elif stars is None or stars <= 0:
                reason = "Modified stars unavailable"
            elif abs(stars - target) > STAR_WINDOW + 1e-12:
                reason = "Outside star window"
            elif relevance is None or not 0 <= relevance <= 1 or skill not in demands:
                reason = "Target demand or relevance unknown"
            elif relevance < min_relevance:
                reason = "Insufficient target relevance"
            elif any(k not in demands for k in assessed):
                reason = "Assessed map demand unknown"
            elif target_bpm is not None and (_speed_bpm(row) or 0) < SPEED_MIN_TEMPO_RATIO * target_bpm:
                reason = "Tapping tempo too far below target"
            if reason:
                data["excluded"][reason] = data["excluded"].get(reason, 0) + 1
                continue
            wanted = data["target_demand"]
            terms = {
                "stars": -(((stars - target) / STAR_SCALE) ** 2),
                "skill": -(((demands[skill] - wanted) / SKILL_SCALE) ** 2),
            }
            bottlenecks = _bottlenecks(skill, assessed, demands, abilities, data["margin"])
            risk = sum(part["risk"] for part in bottlenecks)
            h = history.get(config_id, 1.0)
            terms["bottlenecks"] = -RISK_WEIGHT * risk
            terms["history"] = HISTORY_WEIGHT * (h - 1)
            result = {
                **row,
                "skill": skill,
                "url": map_url(row),
                "skill_demand": demands[skill],
                "relevance": relevance,
                "formula_score": sum(terms.values()),
                "breakdown": {
                    "id": config_id,
                    "mods": row["mods"],
                    "rate": row["rate"],
                    "terms": terms,
                    "risk": risk,
                    "bottlenecks": bottlenecks,
                    "demands": demands,
                    "abilities": {k: abilities[k] for k in assessed},
                    "demand_projection": projections,
                    "target_stars": target,
                    "target_demand": wanted,
                    "reachable_demand": wanted,
                    "target_speed_bpm": target_bpm,
                    "minimum_speed_bpm": SPEED_MIN_TEMPO_RATIO * target_bpm if target_bpm else None,
                    "kappa_s": kappa,
                    "star_window": STAR_WINDOW,
                    "star_scale": STAR_SCALE,
                    "skill_scale": SKILL_SCALE,
                    "other_margin": data["margin"],
                    "risk_weight": RISK_WEIGHT,
                    "history_weight": HISTORY_WEIGHT,
                    "history": h,
                    "history_source": "Matching configuration replay accuracy / 0.95 (capped at 1.10)"
                    if config_id in history
                    else "Neutral assumption",
                },
            }
            previous = best[goal].get(md5)
            if previous is None or _modified_sort_key(result) < _modified_sort_key(previous):
                best[goal][md5] = result
    _finalize_modified_goals(goals, best, limit)
    for data in goals.values():
        del data["margin"]
    return {"skill_adjusted_stars": adjusted, "goals": goals, "candidate_count": count, "result_limit": limit}


def _modified_sort_key(row: dict) -> tuple[float, str]:
    return -row["formula_score"], row["configuration_id"]


def _finalize_modified_goals(goals: dict, best: dict[str, dict[str, dict]], limit: int) -> None:
    """Choose a map's stages after every configuration has competed for its best fit."""
    original = {goal: set(rows) for goal, rows in best.items()}
    all_maps = set().union(*(rows.keys() for rows in best.values()))

    def gap(first: str, second: str, md5: str) -> int:
        # Search rates use hundredths; integer comparison makes the 0.15 boundary exact.
        return abs(round(best[first][md5]["rate"] * 100) - round(best[second][md5]["rate"] * 100))

    for md5 in all_maps:
        warm = md5 in best["Warm-up"]
        comfort = md5 in best["Comfort"]
        push = md5 in best["Push"]
        if warm and comfort and push:
            del best["Warm-up"][md5]
        elif warm and comfort and gap("Warm-up", "Comfort", md5) <= 15:
            del best["Warm-up"][md5]
        elif warm and push and not comfort and gap("Warm-up", "Push", md5) <= 15:
            del best["Warm-up"][md5]

        if comfort and push:
            removed = "Comfort" if gap("Comfort", "Push", md5) >= 15 else "Push"
            del best[removed][md5]

    for goal, rows in best.items():
        data = goals[goal]
        data["eligible"] = len(rows)
        data["maps"] = sorted(rows.values(), key=_modified_sort_key)[:limit]
        # Qualification exclusions count configurations; this reason counts maps reassigned to another stage.
        reassigned = len(original[goal] - rows.keys())
        if reassigned:
            data["excluded"]["Shown in another stage"] = reassigned
