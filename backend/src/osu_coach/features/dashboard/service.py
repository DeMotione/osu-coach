"""The analysis pages (Overview, Aim, Tapping, Sliders & Reading) built from the profile."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import pandas as pd

from osu_coach.common import clicks as shared_clicks
from osu_coach.common import frames
from osu_coach.common.clicks import Clicks
from osu_coach.common.convert import flag, integer, iso, num, nums, text
from osu_coach.common.maps import map_rows
from osu_coach.common.texts import SKILL_LABELS, explain, message
from osu_coach.domain.maps.skillset import recommend
from osu_coach.domain.maps.suggestions import targets_from_profile
from osu_coach.domain.player import Profile, weight_table
from osu_coach.domain.player.consistency import star_consistency
from osu_coach.domain.player.ratings import MIN_MAPS, UNRATED, SkillRating
from osu_coach.domain.player.readiness import MAX_GAP, compare_at, default_target, targets
from osu_coach.features.dashboard import charts
from osu_coach.features.dashboard import schemas as S

if TYPE_CHECKING:
    from osu_coach.app.workspace import Workspace


DIR_ANGLE = {
    "right": 0,
    "up-right": 45,
    "up": 90,
    "up-left": 135,
    "left": 180,
    "down-left": 225,
    "down": 270,
    "down-right": 315,
}


# ------------------------------------------------------------------ summary and replays
def summary(ws: Workspace, p: Profile) -> S.ProfileSummary:
    return S.ProfileSummary(
        player_label=ws.player_label,
        replay_set=ws.replay_set(),
        replays=int(p.overview.replays),
        notes=int(p.overview.objects),
        level_stars=num(p.levels.level_stars),
    )


def analysed_replays(p: Profile) -> list[S.AnalysedReplay]:
    m = frames.replays(p)
    rows = []
    for r in m.to_dict("records"):
        rows.append(
            S.AnalysedReplay(
                key=str(r["key"]),
                played_at=iso(r.get("date")),
                map=text(r.get("map_name")) or "",
                mods=text(r.get("mod_string")) or "NM",
                stars=num(r.get("stars")),
                weight=num(r.get("weight")) if num(r.get("weight")) is not None else 1.0,
                accuracy=num(r.get("accuracy")),
                misses=integer(r.get("nmiss")),
                combo=integer(r.get("max_combo")),
                ur=num(r.get("ur")),
                sim_agreement=num(r.get("sim_agreement")),
                path=text(r.get("source_path")) or "",
                beatmap_md5=text(r.get("beatmap_md5")),
            )
        )
    rows.sort(key=lambda r: r.played_at or "", reverse=True)
    return rows


# ------------------------------------------------------------------ skill facts (Overview hover)
def skill_facts(skill: str, row: SkillRating) -> list[str]:
    """The player's own numbers behind a skill rating."""
    if skill == "consistency":
        low, high = num(row.low), num(row.high)
        where = f" of {low:.1f}–{high:.1f}★" if low is not None and high is not None else ""
        facts = [f"{row.maps} different maps{where}, {row.min_maps or 0} needed ({row.plays or 0} plays)"]
        usual, swing = num(row.map_score), num(row.swing)
        if usual is not None and swing is not None:
            facts.append(
                f"on average you keep {num(row.mean_combo) or 0:.0%} of a map's combo (full combo on "
                f"{num(row.full_combo_share) or 0:.0%} of the maps) at {num(row.mean_accuracy) or 0:.1%}"
            )
            facts.append(
                f"usual map score {100 * usual:.0f}, swinging ±{100 * swing:.0f} between maps"
                + (f"; {row.weak_maps} maps under 20% of the combo" if row.weak_maps else "")
            )
        return facts
    facts = [f"{row.maps} relevant map/mod configurations"]
    measured, expected = num(row.measured), num(row.expected)
    if measured is not None and expected is not None:
        if skill == "accuracy":
            if row.hit_single_notes is not None:
                facts.append(f"{row.hit_single_notes:,} hit single notes")
            facts.append(f"{100 * (1 - measured):.3g}% hit as 300s")
            facts.append(
                f"non-300 rate on hit single notes (lower is better): "
                f"{100 * measured:.3g}% vs assumed {100 * expected:.3g}%"
            )
        else:
            facts.append(f"measured {measured:.3g} vs assumed reference {expected:.3g}")
    if row.parts:
        facts.append("measured durations: " + ", ".join(f"{p['duration']} s" for p in row.parts))
    if row.reason:
        facts.append(message(row.reason))
    return facts


# ------------------------------------------------------------------ overview
def overview(p: Profile) -> S.Overview:
    ov, lv = p.overview, p.levels
    level = num(lv.level_stars)
    weights = (
        [S.LevelWeight(stars_off=float(d), weight=float(w)) for d, w in weight_table(level)[1:]]
        if level is not None
        else []
    )
    level_info = S.LevelInfo(
        stars=level,
        detected=num(lv.level_detected),
        override=bool(lv.level_override),
        recent_n=int(lv.level_recent_n or 0),
        band=float(lv.level_band or 0.5),
        sigma=float(lv.level_sigma or 0.5),
        weights=weights,
        replays=len(p.replays),
        weighted_replays=float(ov.weighted_replays),
    )
    kpis = S.OverviewKpis(
        play_minutes=num(ov.play_minutes),
        comfort_stars=num(lv.comfort_stars),
        misses_per_100=num(ov.misses_per_100),
        accuracy=num(ov.accuracy),
    )
    comfort_level = num(lv.comfort_stars) or level
    relative_scores = {key: row.score for key, row in p.skill_ratings.items()} if comfort_level else {}

    def skill_row(k: str) -> S.SkillScore:
        row = p.skill_ratings.get(k, UNRATED)
        score = num(relative_scores.get(k))
        at_least = num(row.at_least) if score is None and comfort_level else None
        if score is not None:
            what = "combo and accuracy held from map to map around your level" if k == "consistency" else None
            text = f"{score:.0f} · {what or '50 = typical for your comfort level'}"
        elif at_least is not None:
            text = f"at least {at_least:.0f} · your maps haven't tested it to its limit yet"
        else:
            text = message(row.reason) or "not enough data"
        return S.SkillScore(
            key=k,
            label=SKILL_LABELS[k],
            score=score,
            score_text=text,
            low_data=score is not None and row.maps < 10,
            too_few_misses=False,
            n=int(row.hit_single_notes or row.maps or 0),
            facts=skill_facts(k, row),
            needs=message(row.needs) if score is None else None,
            at_least=at_least,
        )

    skills = [skill_row(k) for k in SKILL_LABELS]
    few = [SKILL_LABELS.get(k, k) for k, v in p.skill_ratings.items() if v.score is None]
    stam = p.skill_ratings.get("stamina", UNRATED)
    stamina = []
    if stam.score is not None:
        # the durations behind the stamina rating: measured on enough map/mod setups and tested at the level
        stamina = [
            S.StaminaPoint(seconds=float(part["duration"]), bpm=float(part["measured"]), typical=num(part["expected"]))
            for part in stam.parts or []
            if part["maps"] >= MIN_MAPS and not part["untested"]
        ]
    mb = p.miss_breakdown or {}
    total = sum(mb.values()) or 1.0
    raw = getattr(p, "miss_breakdown_raw", {}) or {}
    causes = [
        S.MissCause(cause=k, share=float(v) / total, misses=int(raw.get(k, 0)))
        for k, v in sorted(mb.items(), key=lambda kv: -kv[1])
    ]
    split = p.aim.split or {}
    a, f = split.get("aim"), split.get("speed_aim")
    aim_split = None
    if a and f and a["expected"] > 0 and f["expected"] > 0:
        aim_split = S.AimSplit(fast_ratio=f["all_misses"] / f["expected"], normal_ratio=a["all_misses"] / a["expected"])
    return S.Overview(
        level=level_info,
        kpis=kpis,
        skills=skills,
        few_data=few,
        compare=star_compare(p),
        stamina=stamina,
        sliders_scored=relative_scores.get("sliders") is not None,
        strengths=[SKILL_LABELS[k] for k in p.strengths],
        weaknesses=[SKILL_LABELS[k] for k in p.weaknesses],
        miss_causes=causes,
        aim_split=aim_split,
        sim_exact_share=num(ov.sim_exact_share),
        sim_agreement=num(ov.sim_agreement),
    )


# ------------------------------------------------------------------ comparing with other star ratings
def consistency_at(p: Profile, comfort: float, stars: float, at_comfort: bool) -> S.CompareSkill:
    """Consistency isn't moved from the comfort level like the other skills: it is measured on the player's own maps
    of that star rating (7★ and 7.5★: maps of 7.00–7.99★)."""
    row = star_consistency(p.replays, comfort if at_comfort else stars, comfort=at_comfort)
    base = num(p.skill_ratings.get("consistency", UNRATED).score)
    score = num(row["score"])
    return S.CompareSkill(
        key="consistency",
        score=score,
        change=round(score - base, 1) if score is not None and base is not None else None,
        demand=None,
        maps=int(row["maps"]),
        needs=message(row["needs"]),
    )


def star_compare(p: Profile) -> S.StarCompare:
    """The comfort-level scores moved to each star rating offered, with the chance to pass its maps cleanly."""
    comfort = num(p.levels.comfort_stars)
    if comfort is None:
        return S.StarCompare(comfort=None, max_gap=MAX_GAP, targets=[], default_target=None)
    out = []
    for stars, locked in targets(comfort):
        if locked:
            out.append(
                S.CompareTarget(stars=stars, comfort=False, locked=True, skills=[], weakest=None, pass_chance=None)
            )
            continue
        at_comfort = stars == round(comfort, 1)  # exactly the comfort level, so it shows its own scores
        c = compare_at(p.skill_ratings, comfort, comfort if at_comfort else stars)
        skills = [
            S.CompareSkill(
                key=k, score=num(v["score"]), change=num(v["change"]), demand=num(v["demand"]), maps=None, needs=None
            )
            if v
            else S.CompareSkill(key=k, score=None, change=None, demand=None, maps=None, needs=None)
            for k, v in c["skills"].items()
        ]
        skills.append(consistency_at(p, comfort, stars, at_comfort))
        weakest = min((s for s in skills if s.score is not None), key=lambda s: s.score, default=None)
        out.append(
            S.CompareTarget(
                stars=stars,
                comfort=at_comfort,
                locked=False,
                skills=skills,
                weakest=weakest.key if weakest else None,
                pass_chance=num(c["pass_chance"]),
            )
        )
    return S.StarCompare(comfort=comfort, max_gap=MAX_GAP, targets=out, default_target=default_target(comfort))


# ------------------------------------------------------------------ aim
def aim(ws: Workspace, p: Profile) -> S.AimPage:
    a, wq = p.aim, p.worst_quadrant
    kpis = S.AimKpis(
        jump_miss_rate=num(a.jump_miss_rate),
        near_miss_share=num(a.near_miss_share),
        jump_along_pct=num(a.jump_along_pct),
    )
    worst = None
    if wq:
        worst = S.WorstQuadrant(
            quadrant=wq.quadrant,
            miss_rate=float(wq.miss_rate),
            rest_miss_rate=float(wq.rest_miss_rate),
            relative_risk=num(wq.relative_risk),
            significant=bool(wq.significant),
        )
    q = frames.quadrants(p)
    quadrants = [
        S.QuadrantCell(
            quadrant=k,
            miss_rate=num(q.loc[k, "miss_rate"]),
            misses=float(q.loc[k, "misses"]),
            objects=float(q.loc[k, "objects"]),
        )
        for k in ("top-left", "top-right", "bottom-left", "bottom-right")
    ]
    g = ws.memo("grid", lambda: charts.playfield_grid(p))
    grid = S.PlayfieldGrid(x=g["x"], y=g["y"], rate=[nums(row) for row in g["rate"]])
    d = frames.directions(p)
    directions = [
        S.DirectionRow(
            direction=k, angle=DIR_ANGLE[k], miss_rate=num(d.loc[k, "miss_rate"]), objects=float(d.loc[k, "objects"])
        )
        for k in DIR_ANGLE
    ]
    dist = frames.distances(p).reset_index()
    distances = [
        S.DistanceRow(
            bin=str(r["dbin"]), miss_rate=num(r["miss_rate"]), objects=float(r["objects"]), along=num(r["along"])
        )
        for r in dist.to_dict("records")
    ]
    ang = frames.angles(p).reset_index()
    angles = [
        S.AngleRow(bin=str(r["abin"]), objects=float(r["objects"]), miss_rate=num(r["miss_rate"]))
        for r in ang.to_dict("records")
    ]
    return S.AimPage(
        kpis=kpis,
        worst_quadrant=worst,
        quadrants=quadrants,
        grid=grid,
        directions=directions,
        distances=distances,
        angles=angles,
    )


# ------------------------------------------------------------------ tapping
def _stream_along(part: dict) -> S.StreamAlong:
    lines = []
    for key, B in part["lines"].items():
        pts = [
            S.StreamPoint(x=float(r["x"]), miss_rate=num(r["miss_rate"]), ur=num(r["ur"]), n=int(r["n"]))
            for r in B.to_dict("records")
        ]
        lines.append(S.StreamLine(key=key, points=pts))
    return S.StreamAlong(step=float(part["step"]), lines=lines)


def _stream_speed(p: Profile) -> S.StreamSpeed | None:
    sp, t = frames.stream_profile(p), p.tapping
    if sp is None or sp.empty:
        return None
    rows = []
    for r in sp.to_dict("records"):
        tap = r.get("tap_miss_rate", r.get("miss_rate"))
        rows.append(
            S.StreamSpeedRow(
                bpm=int(r["bpm_bin"]),
                objects=float(r["objects"]),
                tap_miss_rate=num(tap),
                speed_aim_rate=num(r.get("speed_aim_rate", 0.0)),
                ur=num(r.get("ur")),
                ur_best=num(r.get("ur_best")),
                ur_plays=integer(r.get("ur_plays")) or 0,
                ur_trend=num(r.get("ur_trend")),
                weak=bool(flag(r.get("weak"))),
            )
        )
    return S.StreamSpeed(rows=rows, comfort_bpm=num(t.comfort_bpm), limit_bpm=num(t.limit_bpm))


def _fall_behind(ws: Workspace, p: Profile) -> S.FallBehind:
    fb = frames.fall_behind(p)
    curves = fb.get("curves")
    available = curves is not None and len(curves) >= 3 and "abs_err" in curves
    pts = []
    if available:
        pts = [
            S.FallBehindPoint(
                group=str(r["group"]),
                pos=int(r["pos"]),
                abs_err=num(r["abs_err"]),
                err=num(r["err"]),
                miss_rate=num(r["miss_rate"]),
                n=integer(r["n"]) or 0,
            )
            for r in curves.to_dict("records")
        ]
    cb = fb.get("curves_bpm")
    by_speed = []
    if cb is not None and len(cb) >= 3:
        by_speed = [
            S.FallBehindSpeedPoint(
                group=str(r["group"]),
                pos=int(r["pos"]),
                rel_err=num(r["rel_err"]),
                abs_err=num(r["abs_err"]),
                miss_rate=num(r["miss_rate"]),
                n=integer(r["n"]) or 0,
            )
            for r in cb.to_dict("records")
        ]
    speed = charts.fall_behind_by_speed(cb)
    curve = fb.get("curve")
    lo, hi = fb.get("practice_notes") or (None, None)
    comfort = integer(fb.get("comfort_notes"))
    comfortable_maps = practice_maps = None
    if available and comfort and lo:
        pool = ws.pool()
        if not pool.empty:
            t = targets_from_profile(p)
            easy_lo = max(9, int(comfort * 0.6))
            stamina = num(p.skill_ratings.get("stamina", UNRATED).score)
            abilities = {"stamina": stamina} if stamina is not None else {}
            for low, high, goal in ((easy_lo, comfort, "Comfort"), (int(lo), int(hi), "Push")):
                subset = pool[(pool["max_run"] >= low) & (pool["max_run"] <= high)]
                data = recommend(
                    subset.to_dict("records"),
                    t.comfort,
                    abilities,
                    "stamina",
                    ("stamina",),
                    min_relevance=0.0,
                    played=t.played,
                )
                data = explain(data, "stamina", t)["goals"][goal]
                rows = []
                for row in data["maps"]:
                    bpm = num(row.get("stream_bpm")) or num(row.get("burst_bpm")) or 0
                    row["why"] = f"longest stream {int(row['max_run'])} notes at ~{bpm:.0f} BPM (1/4)"
                    rows.append(row)
                listing = S.MapList(
                    min_notes=low, max_notes=high, maps=map_rows(pd.DataFrame(rows)), excluded=data["excluded"]
                )
                if goal == "Comfort":
                    comfortable_maps = listing
                else:
                    practice_maps = listing
    return S.FallBehind(
        available=available,
        start_note=integer(fb.get("start_note")),
        start_seconds=num(fb.get("start_seconds")),
        bpm=num(fb.get("bpm")),
        base_ms=num(fb.get("base_ms")),
        growth_ms=num(fb.get("growth_ms")),
        last_note=int(curve["pos"].max()) if curve is not None and len(curve) else None,
        comfort_notes=comfort,
        practice_notes=[int(lo), int(hi)] if lo is not None and hi is not None else None,
        streams=int(fb.get("streams") or 0),
        curves=pts,
        by_speed=by_speed,
        by_speed_groups=[S.FallBehindSpeedGroup(**g) for g in speed["groups"]],
        worst_speed=speed["worst"],
        comfortable_maps=comfortable_maps,
        practice_maps=practice_maps,
    )


def tapping(ws: Workspace, p: Profile) -> S.TappingPage:
    t = p.tapping
    kpis = S.TappingKpis(
        ur=num(t.ur),
        ur_single=num(t.ur_single),
        ur_streams=num(t.ur_streams),
        mean_error=num(t.mean_error),
        three_hundred_rate_single=num(t.three_hundred_rate_single),
        alternation_in_streams=num(t.alternation_in_streams),
    )
    h = ws.memo("timing", lambda: charts.timing_histogram(p))
    timing = S.TimingHistogram(
        centers=h["centers"],
        n300=h["counts"][300],
        n100=h["counts"][100],
        n50=h["counts"][50],
        total=float(h["total"]),
        share300=num(h["shares"][300]),
        share100=num(h["shares"][100]),
        share50=num(h["shares"][50]),
        mean=num(h["mean"]),
    )
    st = ws.memo("streams", lambda: charts.stream_time_series(p))
    streams = None
    if st is not None:
        streams = S.StreamsOverTime(
            bands=st["bands"],
            band_width=st["band_width"],
            notes=st["notes"],
            map=_stream_along(st["series"]["map"]),
            session=_stream_along(st["series"]["session"]),
        )
    shares = t.key_share or {}
    keys = S.KeyUsage(
        shares=[S.KeyShare(key=str(k), share=float(shares[k])) for k in sorted(shares)],
        hold_ms=num(charts.key_hold_ms(p)),
        press_ms_streams=num(t.press_ms_streams),
        chatter_per_1000=num(t.chatter_per_1000),
    )
    return S.TappingPage(
        kpis=kpis,
        timing=timing,
        streams_over_time=streams,
        stream_speed=_stream_speed(p),
        fall_behind=ws.memo("fall_behind", lambda: _fall_behind(ws, p)),
        keys=keys,
    )


# ------------------------------------------------------------------ sliders & reading
def _slider_part(part: dict | None) -> S.SliderRates | None:
    if part is None:
        return None
    rows = [
        S.SliderBin(bin=str(r["bin"]), head=float(r["head"]), broke=float(r["broke"]), n=int(r["n"]))
        for r in part["rows"].to_dict("records")
    ]
    return S.SliderRates(rows=rows, worst=part["worst"]) if rows else None


def sliders_reading(ws: Workspace, p: Profile) -> S.SlidersReadingPage:
    sl, rd, cs = p.sliders, p.reading, p.consistency
    kpis = S.SliderKpis(
        sliders=int(sl.sliders or 0),
        head_miss_rate=num(sl.head_miss_rate),
        break_rate=num(sl.break_rate),
        end_miss_rate=num(sl.end_miss_rate),
    )
    tot = sum(p.slider_breaks.values()) or 1.0
    breaks = [
        S.BreakShare(reason=k, share=float(v) / tot) for k, v in sorted(p.slider_breaks.items(), key=lambda kv: -kv[1])
    ]
    ar = frames.ar_table(p)
    ar_misses = []
    if ar is not None and len(ar):
        ar_misses = [
            S.ArMissRow(ar=str(r["ar_bin"]), miss_rate=num(r["miss_rate"]), objects=float(r["objects"]))
            for r in ar.reset_index().to_dict("records")
        ]
    rates = ws.memo("sliders", lambda: charts.slider_rates(p)) or {}
    hits = ws.memo("hits_by_ar", lambda: charts.hits_by_ar(p))
    hits_by_ar = [
        S.HitsByAr(
            ar=float(r["ar"]),
            n=int(r["n"]),
            plays=int(r["plays"]),
            r300=float(r["300"]),
            r100=float(r["100"]),
            r50=float(r["50"]),
            miss=float(r["miss"]),
        )
        for r in hits.to_dict("records")
    ]
    reading = S.ReadingKpis(
        dense_miss_rate=num(rd.dense_miss_rate),
        dense_threshold=num(rd.dense_threshold),
        sparse_miss_rate=num(rd.sparse_miss_rate),
        miss_after_miss_ratio=num(cs.miss_after_miss_ratio),
        end_miss_share=num(cs.end_miss_share),
        end_object_share=num(cs.end_object_share),
    )
    return S.SlidersReadingPage(
        kpis=kpis,
        breaks=breaks,
        ar_misses=ar_misses,
        by_length=_slider_part(rates.get("length")),
        by_speed=_slider_part(rates.get("speed")),
        hits_by_ar=hits_by_ar,
        reading=reading,
    )


def clicks(
    ws: Workspace,
    p: Profile,
    view: str,
    stars: tuple[float | None, float | None] = (None, None),
    since: dt.datetime | None = None,
    until: dt.datetime | None = None,
) -> Clicks:
    """Of the plays with ``stars`` ★ played from ``since`` up to ``until`` (all of them, kept until the profile
    changes, when nothing is limited)."""
    if stars == (None, None) and since is None and until is None:
        return ws.memo(f"clicks:{view}", lambda: shared_clicks.clicks(frames.objects(p), view))
    return shared_clicks.clicks(charts.notes_of_plays(p, stars, since, until), view)
