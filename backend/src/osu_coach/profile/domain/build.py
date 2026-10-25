"""``build_profile``: aggregate replay analyses into a :class:`Profile`."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from osu_coach.analysis.domain import ReplayAnalysis
from osu_coach.profile.domain.aim import (
    aim_regression,
    aim_split,
    angle_stats,
    direction_stats,
    distance_stats,
    grid_stats,
    quadrant_stats,
    worst_quadrant,
)
from osu_coach.profile.domain.consistency import _consistency_metrics
from osu_coach.profile.domain.levels import LEVEL_BAND, LEVEL_SIGMA, _levels, clean_pass, detect_level, replay_weight
from osu_coach.profile.domain.misses import _local_eq, fit_miss_model, miss_causes
from osu_coach.profile.domain.model import Profile
from osu_coach.profile.domain.ratings import comfort as rated_comfort
from osu_coach.profile.domain.ratings import ratings as rate_skills
from osu_coach.profile.domain.reading import _reading_metrics, _reading_ratios
from osu_coach.profile.domain.skills import _rank_skills, compute_skills
from osu_coach.profile.domain.stamina import STAMINA_REACH
from osu_coach.profile.domain.stats import _n, _rate, _ur, _w, _wmean, _wquantile, played_notes
from osu_coach.profile.domain.tapping import stream_fall_behind, stream_limits, stream_speed_profile, tapping_metrics


def build_profile(
    analyses: list[ReplayAnalysis], level: float | None = None, weighted: bool = True, with_ratings: bool = True
) -> Profile:
    """Profile of these replays. The player's level is detected from the recent replays
    (:func:`detect_level`) unless ``level`` (★) is given; with ``weighted`` every replay counts by how close
    its star rating is to that level (:func:`replay_weight`), otherwise all count fully."""
    metas = pd.DataFrame([a.meta for a in analyses])
    found = detect_level(metas)
    override = level is not None and bool(np.isfinite(level))
    used = float(level) if override else found["level"]
    if weighted and len(metas) and "stars" in metas:
        weights = replay_weight(metas["stars"].to_numpy(float), used)
    else:
        weights = np.ones(len(metas))
    metas["weight"] = weights
    wmap = dict(zip(metas["key"], weights)) if len(metas) else {}
    objs, prs = [], []
    for a in analyses:
        o = a.objects.copy()
        o["stars"] = a.meta.get("stars", np.nan)
        o["map_ar"] = a.meta.get("ar", np.nan)
        o["rate"] = a.meta.get("rate", 1.0)
        o["date"] = a.meta.get("date")
        o["hidden"] = bool(a.meta.get("mods", 0) & 8)
        o["flashlight"] = bool(a.meta.get("mods", 0) & 1024)
        o["accuracy"] = a.meta.get("accuracy", np.nan)
        o["completed"] = bool(a.meta.get("completed", True))
        o["map_md5"] = a.meta.get("beatmap_md5")
        mc = a.meta.get("map_max_combo") or 0
        o["combo_ratio"] = min(1.0, (a.meta.get("max_combo") or 0) / mc) if mc else np.nan
        o["w"] = wmap.get(a.key, 1.0)
        objs.append(o)
        pr = a.presses.copy()
        pr["w"] = wmap.get(a.key, 1.0)
        prs.append(pr)
    O = pd.concat(objs, ignore_index=True) if objs else pd.DataFrame()
    Pr = pd.concat(prs, ignore_index=True) if prs else pd.DataFrame()
    rates = {a.key: a.meta.get("rate", 1.0) for a in analyses}
    O["local_eq"] = _local_eq(O)
    O["miss_cause"] = miss_causes(O)
    P = played_notes(O)
    W = _w(P)
    misses = P[~P["head_hit"]]
    mw = _w(misses)
    rw = pd.Series(weights, index=metas.index, dtype=float)

    overview = {
        "replays": len(analyses),
        "maps": int(metas["beatmap_md5"].nunique()) if len(metas) else 0,
        "weighted_replays": float(rw.sum()),
        "objects": len(P),
        "head_misses": int(len(misses)),
        "miss_rate": _rate(~P["head_hit"], W),
        "misses_per_100": 100 * _rate(~P["head_hit"], W),
        "accuracy": _wmean(metas["accuracy"], rw) if len(metas) else math.nan,
        "avg_stars": float(np.average(metas["stars"].fillna(0), weights=metas["n_objects"]))
        if "stars" in metas and len(metas)
        else math.nan,
        "max_stars_passed": float(metas.loc[clean_pass(metas), "stars"].max())
        if "stars" in metas and clean_pass(metas).any()
        else math.nan,
        "ur": _ur(P.loc[P["head_hit"], "err_real"], W[P["head_hit"]]),
        "sim_exact_share": float(metas["sim_match"].dropna().astype(float).mean()) if len(metas) else math.nan,
        "sim_agreement": float(pd.to_numeric(metas["sim_agreement"], errors="coerce").mean())
        if len(metas)
        else math.nan,
        "play_minutes": float(metas["length_s"].sum() / 60) if "length_s" in metas else math.nan,
        "first_date": metas["date"].min() if len(metas) else None,
        "last_date": metas["date"].max() if len(metas) else None,
    }
    causes = misses["miss_cause"].fillna("lost")
    miss_breakdown_raw = {k: int(v) for k, v in causes.value_counts().items()}
    miss_breakdown = {k: float(v) for k, v in mw.groupby(causes).sum().sort_values(ascending=False).items()}
    sliders_all = P[P["kind"] == "slider"]
    broke = sliders_all[sliders_all["broke"] == True]  # noqa: E712
    slider_breaks = {k: float(v) for k, v in _w(broke).groupby(broke["break_reason"].fillna("follow")).sum().items()}

    tapping = tapping_metrics(O, Pr, rates)
    sprof = stream_speed_profile(O)
    tapping.update(stream_limits(sprof, tapping.get("ur_single", math.nan)))
    fall = stream_fall_behind(
        O,
        reach_bpm=(tapping["comfort_bpm"] + STAMINA_REACH) if tapping.get("comfort_bpm") else tapping.get("limit_bpm"),
    )

    q = quadrant_stats(O)
    wq = worst_quadrant(q)
    reg = aim_regression(O)
    jumps = P[P["pattern"].isin(["jump", "spaced"])]
    jw = _w(jumps)
    ss = P["spaced_stream"].astype(bool)
    fs = P["from_slider"] == True  # noqa: E712
    hit = P["head_hit"].astype(bool)
    aim = {
        "aim_miss_rate": _rate(P["miss_cause"] == "aim", W),
        "aim_miss_share": _rate(misses["miss_cause"] == "aim", mw) if len(misses) else math.nan,
        "speed_aim_miss_share": _rate(misses["miss_cause"] == "speed_aim", mw) if len(misses) else math.nan,
        "near_miss_share": _rate(misses["miss_dist"] <= 1.4, mw) if len(misses) else math.nan,
        "jump_objects": int(round(jw.sum())),
        "jump_miss_rate": _rate(~jumps["head_hit"], jw),
        "jump_along": _wmean(jumps["along"], jw) if len(jumps) else math.nan,
        "jump_along_pct": _wquantile(jumps["along"] * jumps["radius"] / jumps["dist"], jw, 0.5) * 100
        if len(jumps)
        else math.nan,
        "aim_err_median": _wquantile(P.loc[hit, "aim_err"], W[hit], 0.5) if len(P) else math.nan,
        "after_slider_miss_rate": _rate(~P.loc[fs, "head_hit"], W[fs]),
        "spaced_stream_objects": int(round(W[ss].sum())),
        "spaced_stream_miss_rate": _rate(~P.loc[ss, "head_hit"], W[ss]),
    }
    sw_all = _w(sliders_all)
    sl_hit = sliders_all["head_hit"].astype(bool)
    slider_metrics = {
        "sliders": int(round(sw_all.sum())),
        "head_miss_rate": _rate(~sl_hit, sw_all),
        "break_rate": float(_n(broke) / max(float(sw_all[sl_hit].sum()), 1e-9)) if len(sliders_all) else math.nan,
        "end_miss_rate": _rate(sliders_all.loc[sl_hit, "end_hit"] == False, sw_all[sl_hit]),  # noqa: E712
    }
    reading = _reading_metrics(P, misses)
    consistency = _consistency_metrics(P, metas)
    model = fit_miss_model(P)
    reading.update(_reading_ratios(P, model))
    skills = compute_skills(P, model, tapping, slider_metrics, reading, consistency, level=used, presses=Pr)
    aim.update(aim_split(P, model))
    strengths, weaknesses = _rank_skills(skills)
    levels = _levels(metas, P, model)
    levels.update(
        level_stars=used,
        level_detected=found["level"],
        level_override=override,
        level_recent_n=found["recent_n"],
        level_recent_since=found["recent_since"],
        level_band=LEVEL_BAND,
        level_sigma=LEVEL_SIGMA,
        weighted=bool(weighted),
    )
    skill_ratings = {}
    if with_ratings:
        comfort = rated_comfort(metas)
        levels["comfort_stars"] = float(level) if override else comfort
        levels["comfort_source"] = "Manual override" if override else "Recent successful map/mod configurations"
        skill_ratings = rate_skills(O, metas, float(level) if override else comfort)
    return Profile(
        overview=overview,
        replays=metas,
        miss_breakdown=miss_breakdown,
        slider_breaks=slider_breaks,
        tapping=tapping,
        stream_profile=sprof,
        aim=aim,
        quadrants=q,
        worst_quadrant=wq,
        grid=grid_stats(O),
        directions=direction_stats(O),
        distances=distance_stats(O),
        angles=angle_stats(O),
        regression=reg,
        sliders=slider_metrics,
        reading=reading,
        consistency=consistency,
        skills=skills,
        strengths=strengths,
        weaknesses=weaknesses,
        levels=levels,
        objects=O,
        presses=Pr,
        model=model,
        miss_breakdown_raw=miss_breakdown_raw,
        fall_behind=fall,
        skill_ratings=skill_ratings,
    )
