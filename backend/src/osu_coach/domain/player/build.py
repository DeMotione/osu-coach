"""``build_profile``: aggregate replay analyses into a :class:`Profile`."""

from __future__ import annotations

import math
from collections import Counter

import numpy as np

from osu_coach.domain.analysis.models import Play
from osu_coach.domain.player.aim import (
    angle_table,
    direction_table,
    distance_table,
    grid_table,
    jump_metrics,
    quadrant_table,
    regression,
    worst_quadrant,
)
from osu_coach.domain.player.levels import LEVEL_BAND, LEVEL_SIGMA, clean_pass, comfort, replay_weight
from osu_coach.domain.player.miss_notes import (
    MissNotes,
    aim_split,
    consistency_metrics,
    fit_miss_model,
    reading_metrics,
    skill_levels,
)
from osu_coach.domain.player.moments import Moments, weighted_std
from osu_coach.domain.player.profile import (
    Aim,
    Consistency,
    FallBehind,
    Levels,
    Overview,
    Profile,
    Reading,
    Sliders,
    Tapping,
)
from osu_coach.domain.player.ratings import combine_ratings, strengths_and_weaknesses
from osu_coach.domain.player.records import PressLengths
from osu_coach.domain.player.stamina import STAMINA_REACH
from osu_coach.domain.player.streams import fall_behind, speed_profile, stream_limits
from osu_coach.domain.player.summary import ChartNotes, PlaySummary, summarize
from osu_coach.domain.player.tapping import press_metrics, timing_metrics


def build_profile(
    analyses: list[Play], level: float | None = None, weighted: bool = True, with_ratings: bool = True
) -> Profile:
    """:func:`build_profile_from` the summaries of these analysed plays."""
    return build_profile_from([summarize(a) for a in analyses], level, weighted, with_ratings)


def build_profile_from(
    summaries: list[PlaySummary], level: float | None = None, weighted: bool = True, with_ratings: bool = True
) -> Profile:
    """Profile of these replays. The player's level is their comfort level (:func:`comfort`, measured or
    provisional) unless ``level`` (★) is given; with ``weighted`` every replay counts by how close its star rating
    is to that level (:func:`replay_weight`), otherwise all count fully. The skill ratings need a measured comfort
    level (or ``level``)."""
    replays = tuple(sm.meta for sm in summaries)
    found = comfort(replays)
    override = level is not None and bool(np.isfinite(level))
    used = float(level) if override else found.stars
    stars = np.array([m.stars for m in replays], dtype=float)
    weights = replay_weight(stars, used) if weighted and replays else np.ones(len(replays))
    wmap = dict(zip([m.key for m in replays], weights.tolist(), strict=True))
    weighted_notes = [(sm.notes, wmap.get(sm.key, 1.0)) for sm in summaries]
    w_notes = sum(w * n.notes for n, w in weighted_notes)
    w_misses = sum(w * n.misses for n, w in weighted_notes)
    overview = _overview(replays, weights, summaries, wmap)
    overview.update(
        objects=sum(n.notes for n, _ in weighted_notes),
        head_misses=sum(n.misses for n, _ in weighted_notes),
        miss_rate=w_misses / w_notes if w_notes > 0 else math.nan,
        misses_per_100=100 * w_misses / w_notes if w_notes > 0 else math.nan,
    )
    raw_causes: Counter[str] = Counter()
    weighted_causes: dict[str, float] = {}
    breaks: dict[str, float] = {}
    for n, w in weighted_notes:
        raw_causes.update(n.miss_causes)
        for cause, count in n.miss_causes.items():
            weighted_causes[cause] = weighted_causes.get(cause, 0.0) + w * count
        for reason, count in n.slider_breaks.items():
            breaks[reason] = breaks.get(reason, 0.0) + w * count
    miss_breakdown_raw = dict(raw_causes.most_common())
    miss_breakdown = dict(sorted(weighted_causes.items(), key=lambda kv: -kv[1]))
    slider_breaks = dict(sorted(breaks.items()))

    tapping = press_metrics([(sm.presses, wmap.get(sm.key, 1.0)) for sm in summaries])
    tapping.update(timing_metrics([(sm.timing, wmap.get(sm.key, 1.0)) for sm in summaries]))
    stream_parts = [(sm.streams, wmap.get(sm.key, 1.0)) for sm in summaries]
    sprof = speed_profile(stream_parts)
    tapping.update(stream_limits(sprof, tapping.get("ur_single", math.nan)))
    fall = fall_behind(
        stream_parts,
        (tapping["comfort_bpm"] + STAMINA_REACH) if tapping.get("comfort_bpm") else tapping.get("limit_bpm"),
    )

    aim_parts = [(sm.aim, wmap.get(sm.key, 1.0)) for sm in summaries]
    q = quadrant_table(aim_parts)
    wq = worst_quadrant(q)
    jump_parts = [(sm.jumps, wmap.get(sm.key, 1.0)) for sm in summaries]
    reg = regression(jump_parts)
    aim = jump_metrics(jump_parts, w_notes, w_misses)
    w_sliders = sum(w * n.sliders for n, w in weighted_notes)
    w_heads = sum(w * n.slider_heads_hit for n, w in weighted_notes)
    w_breaks = sum(w * sum(n.slider_breaks.values()) for n, w in weighted_notes)
    w_end_misses = sum(w * n.slider_end_misses for n, w in weighted_notes)
    any_sliders = any(n.sliders for n, _ in weighted_notes)
    slider_metrics = {
        "sliders": int(round(w_sliders)),
        "head_miss_rate": (w_sliders - w_heads) / w_sliders if w_sliders > 0 else math.nan,
        "break_rate": w_breaks / max(w_heads, 1e-9) if any_sliders else math.nan,
        "end_miss_rate": w_end_misses / w_heads if w_heads > 0 else math.nan,
    }
    M = MissNotes.concat([sm.miss.replace(w=wmap.get(sm.key, 1.0)) for sm in summaries])
    model = fit_miss_model(M.eq, M.missed, M.w)
    reading = reading_metrics(M, model)
    consistency = consistency_metrics(M, [m.accuracy for m in replays])
    levels = skill_levels(M) if replays else {"aim_level": math.nan, "speed_level": math.nan}
    levels["model_coef"] = getattr(model, "coef", None)
    levels.update(
        level_stars=used,
        level_detected=found.stars,
        level_override=override,
        level_recent_n=found.recent_n,
        level_recent_since=found.recent_since,
        level_band=LEVEL_BAND,
        level_sigma=LEVEL_SIGMA,
        weighted=bool(weighted),
    )
    # the comfort level the ratings are measured against: set by hand, or measured (never a provisional estimate)
    levels["comfort_stars"] = float(level) if override else found.measured
    levels["comfort_status"] = "override" if override else found.status
    levels["comfort_setups"] = found.setups
    levels["comfort_source"] = "Manual override" if override else "Recent successful map/mod configurations"
    skill_ratings = (
        combine_ratings([sm.ratings for sm in summaries], replays, levels["comfort_stars"]) if with_ratings else {}
    )
    strengths, weaknesses = strengths_and_weaknesses(skill_ratings)
    return Profile(
        overview=Overview(**overview),
        replays=replays,
        weights=tuple(weights.tolist()),
        miss_breakdown=miss_breakdown,
        slider_breaks=slider_breaks,
        tapping=Tapping(**tapping),
        stream_profile=sprof,
        aim=Aim(**aim, split=aim_split(M, model)),
        quadrants=q,
        worst_quadrant=wq,
        grid=grid_table(aim_parts),
        directions=direction_table(aim_parts),
        distances=distance_table(jump_parts),
        angles=angle_table(aim_parts),
        regression=reg,
        sliders=Sliders(**slider_metrics),
        reading=Reading(**reading),
        consistency=Consistency(**consistency),
        strengths=strengths,
        weaknesses=weaknesses,
        levels=Levels(**levels),
        notes=ChartNotes.concat([sm.chart.replace(w=wmap.get(sm.key, 1.0)) for sm in summaries]),
        presses=PressLengths.concat(
            [PressLengths(np.full(len(sm.press_lengths), sm.key, dtype=object), sm.press_lengths) for sm in summaries]
        ),
        miss_breakdown_raw=miss_breakdown_raw,
        fall_behind=FallBehind(**fall),
        skill_ratings=skill_ratings,
    )


def _ur_of(parts: list[tuple[Moments, float]]) -> float:
    """UR (10 × the standard deviation of the hit errors) of these plays' hits, each weighted by its play's weight;
    NaN with 5 hits or fewer."""
    std, count = weighted_std(parts)
    return 10 * std if count > 5 else math.nan


def _overview(replays, weights: np.ndarray, summaries: list, wmap: dict) -> dict:
    """What the plays add up to (the per-note counts are added by the caller)."""

    def values(name: str) -> np.ndarray:
        return np.array([getattr(m, name) for m in replays], dtype=float)

    acc, stars, n_objects = values("accuracy"), values("stars"), values("n_objects")
    ok = ~np.isnan(acc)
    passed = [m.stars for m in replays if clean_pass(m) and math.isfinite(m.stars)]
    matched = [float(m.sim_match) for m in replays if m.sim_match is not None]
    agreement = values("sim_agreement")
    dates = [m.date for m in replays if m.date is not None]
    return {
        "replays": len(replays),
        "maps": len({m.beatmap_md5 for m in replays}),
        "weighted_replays": float(weights.sum()),
        "accuracy": float((acc[ok] * weights[ok]).sum() / weights[ok].sum())
        if ok.any() and weights[ok].sum() > 0
        else math.nan,
        "avg_stars": float(np.average(np.nan_to_num(stars), weights=n_objects)) if replays else math.nan,
        "max_stars_passed": float(max(passed)) if passed else math.nan,
        "ur": _ur_of([(sm.timing.hit_errors, wmap.get(sm.key, 1.0)) for sm in summaries]),
        "sim_exact_share": float(np.mean(matched)) if matched else math.nan,
        "sim_agreement": float(np.nanmean(agreement)) if (~np.isnan(agreement)).any() else math.nan,
        "play_minutes": float(np.nansum(values("length_s")) / 60) if replays else math.nan,
        "first_date": min(dates) if dates else None,
        "last_date": max(dates) if dates else None,
    }
