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
from dataclasses import dataclass, field
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


@dataclass(frozen=True, slots=True)
class Bottleneck:
    """Another assessed skill's overload on a map: only what it asks beyond the player's rating plus the goal's
    margin counts."""

    skill: str
    demand: float
    ability: float
    margin: float
    overload: float
    risk: float  # (overload / sigma)²
    sigma: float = 20.0
    importance: float = 1.0


@dataclass(frozen=True, slots=True)
class DemandProjection:
    """How a map's demand of a skill was projected from its pool feature: against the feature of typical maps
    (``reference_median``), or for speed from its tapping tempo against the comfort level's (``reference_bpm``)."""

    raw_feature: float
    reference_median: float | None = None
    star_points: int | None = None
    feature_points: int | None = None
    reference_bpm: float | None = None
    points_per_doubling: float | None = None
    source: str | None = None


@dataclass(frozen=True, slots=True)
class Terms:
    """The terms of the score F(m) (each ≤ 0 but ``history``)."""

    stars: float
    skill: float
    bottlenecks: float
    history: float

    @property
    def total(self) -> float:
        return self.stars + self.skill + self.bottlenecks + self.history


@dataclass(frozen=True, slots=True)
class Breakdown:
    """F(m) of one map configuration with its inputs (shown with the map as "Breakdown")."""

    id: str  # the configuration
    mods: str
    rate: float
    terms: Terms
    risk: float
    bottlenecks: tuple[Bottleneck, ...]
    demands: dict[str, float]
    abilities: dict[str, float]
    demand_projection: dict[str, DemandProjection]
    target_stars: float
    target_demand: float
    reachable_demand: float
    target_speed_bpm: float | None
    minimum_speed_bpm: float | None
    kappa_s: float
    star_window: float
    star_scale: float
    skill_scale: float
    other_margin: float
    risk_weight: float
    history_weight: float
    history: float
    history_source: str


@dataclass(frozen=True, slots=True)
class RankedMap:
    """A map configuration picked for a goal. ``map`` is its pool row (or the row of the modified variant): the
    map's metadata and the pattern features the ranking and the ``why`` text read."""

    map: Mapping[str, Any]
    configuration_id: str
    mods: str
    rate: float
    skill: str
    url: str
    skill_demand: float
    relevance: float
    formula_score: float
    breakdown: Breakdown
    why: str = ""

    @property
    def md5(self) -> str:
        return str(self.map["md5"])


@dataclass(frozen=True, slots=True)
class GoalMaps:
    """The maps of one goal (Warm-up / Comfort / Push), best first, and how many maps each reason left out."""

    target_stars: float | None
    target_demand: float | None
    star_min: float | None
    star_max: float | None
    eligible: int
    excluded: dict[str, int]
    maps: tuple[RankedMap, ...]


@dataclass(frozen=True, slots=True)
class Recommendation:
    """What a recommender found: the maps of every goal. ``result_limit``: the most maps kept per goal (modified
    search only)."""

    skill_adjusted_stars: float | None
    goals: dict[str, GoalMaps]
    candidate_count: int
    result_limit: int | None = None


def _bottlenecks(
    skill: str, assessed: tuple[str, ...], demands: Mapping[str, float], abilities: Mapping[str, float], margin: float
) -> tuple[Bottleneck, ...]:
    """The other skills' overload: only what a map asks beyond the player's rating plus the goal's margin."""
    out = []
    for other in assessed:
        if other == skill:
            continue
        overload = max(0.0, demands[other] - (abilities[other] + margin))
        out.append(
            Bottleneck(
                skill=other,
                demand=demands[other],
                ability=abilities[other],
                margin=margin,
                overload=overload,
                risk=(overload / 20.0) ** 2,
            )
        )
    return tuple(out)


def _rank(
    row: Mapping[str, Any],
    stars: float,
    skill: str,
    assessed: tuple[str, ...],
    demands: dict[str, float],
    relevance: float,
    projection: dict[str, DemandProjection],
    abilities: Mapping[str, float],
    *,
    configuration_id: str,
    mods: str,
    rate: float,
    target: float,
    wanted: float,
    target_bpm: float | None,
    kappa: float,
    margin: float,
    history: float,
    history_source: str,
) -> RankedMap:
    """F(m) of one map configuration for a goal (target stars ``target``, target demand ``wanted``)."""
    bottlenecks = _bottlenecks(skill, assessed, demands, abilities, margin)
    risk = sum(b.risk for b in bottlenecks)
    terms = Terms(
        stars=-(((stars - target) / STAR_SCALE) ** 2),
        skill=-(((demands[skill] - wanted) / SKILL_SCALE) ** 2),
        bottlenecks=-RISK_WEIGHT * risk,
        history=HISTORY_WEIGHT * (history - 1),
    )
    return RankedMap(
        map=row,
        configuration_id=configuration_id,
        mods=mods,
        rate=rate,
        skill=skill,
        url=map_url(row),
        skill_demand=demands[skill],
        relevance=relevance,
        formula_score=terms.total,
        breakdown=Breakdown(
            id=configuration_id,
            mods=mods,
            rate=rate,
            terms=terms,
            risk=risk,
            bottlenecks=bottlenecks,
            demands=demands,
            abilities={k: abilities[k] for k in assessed},
            demand_projection=projection,
            target_stars=target,
            target_demand=wanted,
            reachable_demand=wanted,
            target_speed_bpm=target_bpm,
            minimum_speed_bpm=SPEED_MIN_TEMPO_RATIO * target_bpm if target_bpm else None,
            kappa_s=kappa,
            star_window=STAR_WINDOW,
            star_scale=STAR_SCALE,
            skill_scale=SKILL_SCALE,
            other_margin=margin,
            risk_weight=RISK_WEIGHT,
            history_weight=HISTORY_WEIGHT,
            history=history,
            history_source=history_source,
        ),
    )


@dataclass(frozen=True, slots=True)
class _Candidate:
    """A pool map with what it demands of the assessed skills and how relevant it is to each."""

    row: Mapping[str, Any]
    demands: dict[str, float]
    relevance: dict[str, float]
    projection: dict[str, DemandProjection]


def _candidates(
    pool: Sequence[Mapping[str, Any]], theta: float, assessed: tuple[str, ...]
) -> tuple[list[_Candidate], dict[str, int]]:
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
        demands: dict[str, float] = {}
        relevance: dict[str, float] = {}
        projection: dict[str, DemandProjection] = {}
        for skill in assessed:
            value = features.get(skill)
            ref = refs.get(skill)
            affinity = finite_or_none(row.get("s_" + skill))
            if value is None or affinity is None or not 0 <= affinity <= 1 or (skill != "speed" and ref is None):
                continue
            demands[skill] = _demand(skill, value, row["stars"], theta, ref)
            relevance[skill] = affinity
            if skill == "speed":
                projection[skill] = DemandProjection(
                    raw_feature=value,
                    reference_bpm=expected_speed_bpm(theta),
                    points_per_doubling=SPEED_POINTS,
                    source="third_fastest_run" if "speed_runs" in row else "legacy_pool_bpm_proxy",
                )
            else:
                projection[skill] = DemandProjection(
                    raw_feature=value, reference_median=ref, star_points=20, feature_points=FEATURE_POINTS[skill]
                )
        result.append(_Candidate(row, demands, relevance, projection))
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
) -> Recommendation:
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
        excluded: dict[str, int] = dict(rejected)
        eligible = []
        for candidate in candidates:
            row, demands, relevance = candidate.row, candidate.demands, candidate.relevance
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
            elif target is None or abs(stars - target) > STAR_WINDOW + 1e-12:
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
        ranked = []
        for c in eligible:
            md5 = str(c.row["md5"])
            configuration_id = Configuration(md5).key
            ranked.append(
                _rank(
                    c.row,
                    c.row["stars"],
                    skill,
                    assessed,
                    c.demands,
                    c.relevance[skill],
                    c.projection,
                    abilities,
                    configuration_id=configuration_id,
                    mods="NM",
                    rate=1.0,
                    target=target,
                    wanted=wanted,
                    target_bpm=target_speed_bpm,
                    kappa=kappa,
                    margin=margin,
                    history=1.0,
                    history_source="Neutral assumption",
                )
            )
        ranked.sort(key=lambda m: (-m.formula_score, m.md5 + "@NM"))
        if low_accuracy and not ranked and target is not None and all(other in abilities for other in assessed):
            excluded["No qualified timing map in the configured star window"] = 1
        result[goal] = GoalMaps(
            target_stars=target,
            target_demand=wanted,
            star_min=target - STAR_WINDOW if target is not None else None,
            star_max=target + STAR_WINDOW if target is not None else None,
            eligible=len(ranked),
            excluded=excluded,
            maps=tuple(ranked),
        )
    return Recommendation(skill_adjusted_stars=adjusted, goals=result, candidate_count=len(candidates))


@dataclass(slots=True)
class _Stage:
    """A goal of the modified search while the configurations compete for it."""

    target_stars: float | None
    target_demand: float | None
    margin: float
    excluded: dict[str, int] = field(default_factory=dict)
    maps: list[RankedMap] = field(default_factory=list)
    eligible: int = 0

    def result(self) -> GoalMaps:
        target = self.target_stars
        return GoalMaps(
            target_stars=target,
            target_demand=self.target_demand,
            star_min=target - STAR_WINDOW if target is not None else None,
            star_max=target + STAR_WINDOW if target is not None else None,
            eligible=self.eligible,
            excluded=self.excluded,
            maps=tuple(self.maps),
        )


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
) -> Recommendation:
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
    stages = {}
    for goal, (star_offset, skill_offset, margin) in GOALS.items():
        target = adjusted + star_offset if adjusted is not None else None
        if target is not None and target <= 0:
            raise ValueError("The adjusted target stars must be positive.")
        stages[goal] = _Stage(target, abilities[skill] + skill_offset if skill in abilities else None, margin)
    if missing:
        reason = "Target player rating unknown" if skill in missing else "Assessed player rating unknown"
        for stage in stages.values():
            stage.excluded[reason] = 1
        goals = {goal: stage.result() for goal, stage in stages.items()}
        return Recommendation(skill_adjusted_stars=adjusted, goals=goals, candidate_count=0, result_limit=limit)
    count = 0
    best: dict[str, dict[str, RankedMap]] = {goal: {} for goal in stages}
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
            projections[key] = DemandProjection(
                raw_feature=value, reference_median=ref, star_points=20, feature_points=FEATURE_POINTS.get(key)
            )
        for goal, stage in stages.items():
            target = stage.target_stars
            target_bpm = speed_bpm_for_rating(stage.target_demand, theta) if skill == "speed" else None
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
                stage.excluded[reason] = stage.excluded.get(reason, 0) + 1
                continue
            result = _rank(
                row,
                stars,
                skill,
                assessed,
                demands,
                relevance,
                projections,
                abilities,
                configuration_id=config_id,
                mods=row["mods"],
                rate=row["rate"],
                target=target,
                wanted=stage.target_demand,
                target_bpm=target_bpm,
                kappa=kappa,
                margin=stage.margin,
                history=history.get(config_id, 1.0),
                history_source="Matching configuration replay accuracy / 0.95 (capped at 1.10)"
                if config_id in history
                else "Neutral assumption",
            )
            previous = best[goal].get(md5)
            if previous is None or _modified_sort_key(result) < _modified_sort_key(previous):
                best[goal][md5] = result
    _finalize_modified_goals(stages, best, limit)
    goals = {goal: stage.result() for goal, stage in stages.items()}
    return Recommendation(skill_adjusted_stars=adjusted, goals=goals, candidate_count=count, result_limit=limit)


def _modified_sort_key(m: RankedMap) -> tuple[float, str]:
    return -m.formula_score, m.configuration_id


def _finalize_modified_goals(stages: Mapping[str, _Stage], best: dict[str, dict[str, RankedMap]], limit: int) -> None:
    """Choose a map's stages after every configuration has competed for its best fit."""
    original = {goal: set(rows) for goal, rows in best.items()}
    all_maps = set().union(*(rows.keys() for rows in best.values()))

    def gap(first: str, second: str, md5: str) -> int:
        # Search rates use hundredths; integer comparison makes the 0.15 boundary exact.
        return abs(round(best[first][md5].rate * 100) - round(best[second][md5].rate * 100))

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
        stage = stages[goal]
        stage.eligible = len(rows)
        stage.maps = sorted(rows.values(), key=_modified_sort_key)[:limit]
        # Qualification exclusions count configurations; this reason counts maps reassigned to another stage.
        reassigned = len(original[goal] - rows.keys())
        if reassigned:
            stage.excluded["Shown in another stage"] = reassigned
