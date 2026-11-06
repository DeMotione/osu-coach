"""The skill ratings: comfort-relative replay abilities, adapted from osu-skill-lab.

Each skill is scored against what is typical at the player's comfort level (50 = typical), not against other
players and not as a full-combo chance. A skill stays ``None`` when the replays don't cover or challenge it enough.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from osu_coach.domain.analysis.models import ReplayMeta
from osu_coach.domain.analysis.notes import HitObjects
from osu_coach.domain.player.algorithm import DT_ACCURACY_MIN
from osu_coach.domain.player.consistency import star_consistency
from osu_coach.domain.player.demand import log_demand
from osu_coach.domain.player.levels import replay_weight
from osu_coach.domain.player.messages import Message
from osu_coach.domain.player.records import SkillRating, StaminaPart
from osu_coach.domain.player.skill_scale import SPEED_POINTS, expected_speed_bpm
from osu_coach.domain.player.skill_values import (
    PlayContext,
    aim_value,
    cursor_speed,
    flow_mask,
    flow_value,
    jumps_mask,
    reading_value,
    slider_difficulty,
    speed_value,
    tempo_curve,
    top,
)

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


def _needs(skill: str, maps: int, untested: bool, tested: float, expected: float) -> Message:
    """What to play to get a score for ``skill``: harder maps when everything played was easier than expected and
    nearly all of it was held, else more maps."""
    if untested:
        return Message("harder_maps", {"skill": skill, "tested": tested, "expected": expected})
    return Message("more_maps", {"skill": skill, "more": max(1, MIN_MAPS - maps)})


def _aggregate(rows: Sequence[RatedPlay]) -> tuple[float | None, list[RatedPlay]]:
    """The best play of every map/mod setup, best first, and their average weighted by rank (``RANK_DECAY``)."""
    best: dict[str, RatedPlay] = {}
    for row in rows:
        if row.value is None or not math.isfinite(row.value):
            continue
        key = str(row.map)
        if key not in best or row.value > best[key].value:
            best[key] = row
    chosen = sorted(best.values(), key=lambda row: row.value, reverse=True)
    weights = np.power(RANK_DECAY, np.arange(len(chosen)))
    return (float(np.average([r.value for r in chosen], weights=weights)) if chosen else None, chosen)


@dataclass(frozen=True, slots=True)
class RatedPlay:
    """One play's value of one skill: what it showed (``value``), how demanding it was (``exposure``) and the share
    of it the player held (``success_share``); ``map`` is its map/mod setup."""

    map: str
    value: float
    exposure: float
    success_share: float


@dataclass(frozen=True, slots=True)
class RatingInputs:
    """What one play adds to the skill ratings."""

    key: str
    map: str
    aim: RatedPlay | None = None
    flow_aim: RatedPlay | None = None
    speed: RatedPlay | None = None
    sliders: RatedPlay | None = None
    reading: RatedPlay | None = None
    tempo: Mapping[int, float] = field(default_factory=dict)  # stamina: fastest tempo kept per duration (s)
    tempo_demand: Mapping[int, float] = field(default_factory=dict)  # ... of the notes, as if every one was pressed
    singles: int = 0  # hit single notes (accuracy), when the play's timing counts
    singles_not_300: int = 0
    od: float = math.nan


def rating_inputs(
    notes: HitObjects, ctx: PlayContext, timing_counts: bool = True, od: float = math.nan
) -> RatingInputs:
    """The :class:`RatingInputs` of one play from its played notes."""
    rated: dict[str, RatedPlay | None] = {}
    hit = notes.head_hit
    move = cursor_speed(notes, clip=False)
    for skill, value, mask, n in (
        ("aim", aim_value(notes, ctx), jumps_mask(notes), 30),
        ("flow_aim", flow_value(notes, ctx), flow_mask(notes), 50),
    ):
        rated[skill] = None
        if value is not None:
            idx = np.flatnonzero(mask)
            share = float(hit[idx[top(move[idx], n)]].mean())
            demand = value.intensity if skill == "aim" else value.speed * value.amount
            rated[skill] = RatedPlay(ctx.map, demand * share**0.8, demand, share)
    speed = speed_value(notes)
    rated["speed"] = None
    if speed is not None:
        runs = notes.stream_bpm[notes.run_len >= 3]
        exposure = float(np.nanmax(runs)) if (~np.isnan(runs)).any() else math.nan
        rated["speed"] = RatedPlay(ctx.map, speed.bpm, exposure, speed.clean / max(1, speed.runs))
    rated["sliders"] = None
    sliders = notes.take((notes.kind == "slider") & hit)
    if len(sliders) >= 10:
        difficulty = slider_difficulty(sliders)
        chosen = top(difficulty, 30)
        demand = float(difficulty[chosen].mean())
        share = float((~sliders.broke[chosen].astype(bool)).mean())
        rated["sliders"] = RatedPlay(ctx.map, demand * share**3, demand, share)
    reading = reading_value(notes, ctx)
    rated["reading"] = (
        RatedPlay(ctx.map, reading.value, reading.ar_factor * reading.bpm_factor, reading.accuracy) if reading else None
    )
    singles = (notes.run_len < 3) & hit if timing_counts else np.zeros(len(notes), dtype=bool)
    return RatingInputs(
        key=ctx.key,
        map=ctx.map,
        tempo=tempo_curve(notes, ctx.rate),
        tempo_demand=tempo_curve(notes, ctx.rate, all_pressed=True),
        singles=int(singles.sum()),
        singles_not_300=int((singles & (notes.head_result != 300)).sum()),
        od=od,
        **rated,
    )


def combine_ratings(
    inputs: Sequence[RatingInputs], replays: Sequence[ReplayMeta], theta: float | None
) -> dict[str, SkillRating]:
    """The ratings from every play's :class:`RatingInputs`, against the comfort level ``theta``."""
    result = {skill: SkillRating(score=None, maps=0, reason=Message("comfort_unknown")) for skill in POINTS}
    result["consistency"] = star_consistency(replays, theta, comfort=True)
    if theta is None or not math.isfinite(theta) or not inputs:
        return result
    stars = np.array([m.stars if m.stars is not None else math.nan for m in replays], dtype=float)
    weight_of = dict(zip([m.key for m in replays], replay_weight(stars, theta), strict=True))
    for skill in ("aim", "flow_aim", "speed", "sliders", "reading"):
        value, chosen = _aggregate([r for i in inputs if (r := getattr(i, skill)) is not None])
        expected = _expected(skill, theta)
        exposure = max((row.exposure for row in chosen if math.isfinite(row.exposure)), default=0.0)
        share = float(np.mean([row.success_share for row in chosen])) if chosen else None
        untested = bool(chosen and skill != "reading" and exposure < expected and share >= 0.95)
        score = _score(skill, value, expected) if len(chosen) >= MIN_MAPS and not untested else None
        result[skill] = SkillRating(
            score=score,
            maps=len(chosen),
            measured=value,
            expected=expected,
            tested_demand=exposure,
            success_share=share,
            # held ~everything played, all of it easier than expected: the skill is at least as good as that
            at_least=_score(skill, exposure, expected) if untested else None,
            needs=None if score is not None else _needs(skill, len(chosen), untested, exposure, expected),
            reason=Message("insufficient_challenge")
            if untested
            else Message("need_maps", {"maps": MIN_MAPS})
            if len(chosen) < MIN_MAPS
            else Message("best_per_setup"),
        )
    result["stamina"] = _stamina(inputs, theta)
    result["accuracy"] = _accuracy(inputs, weight_of, theta)
    return result


def _stamina(inputs: Sequence[RatingInputs], theta: float) -> SkillRating:
    scores = []
    parts: list[StaminaPart] = []
    for duration in STAMINA_SHARES:
        # the fastest tempo kept this long, against the tempo of the notes as if every one was pressed
        rows = [
            RatedPlay(i.map, i.tempo[duration], i.tempo_demand.get(duration, 0.0), math.nan)
            for i in inputs
            if duration in i.tempo
        ]
        value, chosen = _aggregate(rows)
        if value is None:
            continue
        expected = _expected("stamina", theta, duration=duration)
        exposure = max((i.tempo_demand[duration] for i in inputs if duration in i.tempo_demand), default=0.0)
        share = float(np.mean([r.value / max(r.exposure, 1e-6) for r in chosen]))
        untested = exposure < expected and share >= 0.95
        usable = len(chosen) >= MIN_MAPS and not untested
        parts.append(
            StaminaPart(
                duration=duration,
                measured=value,
                maps=len(chosen),
                tested_demand=exposure,
                success_share=share,
                expected=expected,
                untested=untested,
            )
        )
        if usable:
            scores.append(_score("stamina", value, expected))
    # no duration scored, but some only because nothing was demanding enough: a lower bound, and what to play
    open_parts = [d for d in parts if d.untested]
    at_least = (
        round(float(np.mean([_score("stamina", d.tested_demand, d.expected) for d in open_parts])), 1)
        if open_parts and not scores
        else None
    )
    stamina_needs = None
    if not scores:
        first = open_parts[0] if open_parts else None
        stamina_needs = (
            Message(
                "stamina_harder", {"seconds": first.duration, "tested": first.tested_demand, "expected": first.expected}
            )
            if first
            else Message("stamina_maps", {"maps": MIN_MAPS})
        )
    return SkillRating(
        score=round(float(np.mean(scores)), 1) if scores else None,
        maps=len({i.map for i in inputs if i.tempo}),
        parts=tuple(parts),
        at_least=at_least,
        needs=stamina_needs,
        reason=Message("stamina_mean"),
    )


def _accuracy(inputs: Sequence[RatingInputs], weight_of: Mapping[str, float], theta: float) -> SkillRating:
    gate = Message("accuracy_gate", {"heads": 60, "dt_accuracy": DT_ACCURACY_MIN})
    timed = [i for i in inputs if i.singles]
    n = sum(i.singles for i in timed)
    if not n:
        return SkillRating(score=None, maps=0, reason=gate)
    total = sum(weight_of.get(i.key, 1.0) * i.singles for i in timed)
    error = sum(weight_of.get(i.key, 1.0) * i.singles_not_300 for i in timed) / total if total > 0 else math.nan
    window_weights: dict[float, float] = {}
    for i in timed:
        window = max(0.0, 79.5 - 6 * i.od)
        window_weights[window] = window_weights.get(window, 0.0) + weight_of.get(i.key, 1.0) * i.singles
    windows = sorted(window_weights.items())
    expected = _accuracy_expected(windows, theta) if windows else math.nan
    return SkillRating(
        score=_accuracy_score(error, expected, theta) if n >= 60 else None,
        maps=len({i.map for i in timed}),
        hit_single_notes=n,
        measured=error,
        expected=expected,
        expected_top=_accuracy_expected(windows, 10.0) if windows else math.nan,
        od_windows=windows,
        reason=Message("accuracy_measured") if n >= 60 else gate,
    )


STRONG, WEAK = 55.0, 45.0  # a rating this high is a strength, this low a weakness
RANKED = 3  # at most this many of each


def strengths_and_weaknesses(rows: Mapping[str, SkillRating]) -> tuple[list[str], list[str]]:
    """The skills to show as strong and to work on, the same everywhere (Overview, tips, playlists): the best
    ``RANKED`` rated at ``STRONG`` or more and the worst ``RANKED`` rated at ``WEAK`` or less. With three or more
    ratings and none that low, the lowest is still a weakness: there is always one thing to work on."""
    scored = [(skill, float(row.score)) for skill, row in rows.items() if row.score is not None]
    best = sorted(scored, key=lambda item: item[1], reverse=True)
    strengths = [skill for skill, score in best[:RANKED] if score >= STRONG]
    weaknesses = [skill for skill, score in sorted(scored, key=lambda item: item[1])[:RANKED] if score <= WEAK]
    if not weaknesses and len(scored) >= RANKED:
        weaknesses = [best[-1][0]]
    return strengths, weaknesses


def at_level(rows: Mapping[str, SkillRating], theta: float) -> dict[str, float | None]:
    """Rebase measured abilities to another star reference without rereading replays."""
    out: dict[str, float | None] = {}
    for skill, row in rows.items():
        if skill == "stamina":
            scores = []
            for part in row.parts or ():
                expected = _expected(skill, theta, duration=part.duration)
                if part.maps >= MIN_MAPS and not (part.tested_demand < expected and part.success_share >= 0.95):
                    scores.append(_score(skill, part.measured, expected))
            out[skill] = round(float(np.mean(scores)), 1) if scores else None
        elif skill == "accuracy":
            windows = row.od_windows
            out[skill] = (
                _accuracy_score(row.measured, _accuracy_expected(windows, theta), theta)
                if row.score is not None and windows
                else row.score
            )
        elif skill in ("reading", "consistency"):
            out[skill] = row.score
        elif row.maps < MIN_MAPS:
            out[skill] = None
        else:
            expected = _expected(skill, theta)
            untested = (row.tested_demand or 0) < expected and (row.success_share or 0) >= 0.95
            out[skill] = None if untested else _score(skill, row.measured, expected)
    return out
