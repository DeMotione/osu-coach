"""The analysis pages (Overview, Aim, Tapping, Sliders & Reading) built from the profile."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from osu_coach.app.convert import flag, integer, iso, num, nums, text
from osu_coach.dashboard import schemas as S
from osu_coach.insights import domain as insights
from osu_coach.insights import service as insights_service
from osu_coach.insights.schemas import Clicks
from osu_coach.maps.domain import targets_from_profile
from osu_coach.maps.service import map_rows
from osu_coach.maps.skillset import recommend
from osu_coach.profile.domain import SKILL_LABELS, Profile, weight_table
from osu_coach.profile.domain.consistency import BAND_MIN_PLAYS, consistency_bands
from osu_coach.profile.domain.readiness import MAX_GAP, compare_at, default_target, targets
from osu_coach.tips.service import tip_out, tips

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


TOP_TIPS = 3


# ------------------------------------------------------------------ summary and replays
def summary(ws: Workspace, p: Profile) -> S.ProfileSummary:
    return S.ProfileSummary(
        player_label=ws.player_label,
        replay_set=ws.replay_set(),
        replays=int(p.overview["replays"]),
        notes=int(p.overview["objects"]),
        level_stars=num(p.levels.get("level_stars")),
    )


def analysed_replays(p: Profile) -> list[S.AnalysedReplay]:
    m = p.replays
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
def _n(v, spec: str = ".0f") -> str | None:
    f = num(v)
    return None if f is None else format(f, spec)


def _dur(seconds) -> str:
    seconds = float(seconds)
    return f"{seconds:.0f} s" if seconds < 60 else f"{seconds / 60:.0f} min"


def skill_facts(key: str, v: dict) -> list[str]:
    """The player's own numbers behind a skill score."""
    facts = []
    n = v.get("n") or 0
    if key == "accuracy":
        r, ur = _n(v.get("three_hundred_rate"), ".0%"), _n(v.get("ur"))
        facts.append(f"{n:,} single notes" + (f", {r} hit as 300s" if r else "") + (f", UR {ur}" if ur else ""))
    elif key == "sliders":
        br, val, ref = _n(v.get("break_rate"), ".1%"), _n(v.get("value")), _n(v.get("ref"))
        held = _n(v.get("top_held"), ".0%")
        facts.append(f"{n:,} sliders" + (f", {br} broken" if br else ""))
        if val:
            facts.append(
                f"your best {v.get('plays', 0)} maps: hardest sliders worth {val}"
                + (f" (typical for your level: {ref})" if ref else "")
                + (f", {held} of them held" if held else "")
            )
    elif key == "consistency":
        r = _n(v.get("miss_after_miss_ratio"), ".2f")
        facts.append(f"{n:,} notes" + (f", miss-after-miss ratio {r}" if r else ""))
        ch, sd, sp = _n(v.get("chain_score")), _n(v.get("steady_score")), _n(v.get("spread"), ".1f")
        if ch or sd:
            facts.append(
                f"miss chains {ch or '–'}, steadiness between plays {sd or '–'}"
                + (f" (spread {sp} misses / 100 notes)" if sp else "")
            )
    elif key == "reading":
        ar, hit = _n(v.get("lowest_ar"), ".1f"), _n(v.get("bpm_hit"), ".0%")
        facts.append(f"{v.get('maps', 0)} passed maps" + (f", lowest AR {ar}" if ar else ""))
        if v.get("bpm_maps"):
            facts.append(
                f"{v['bpm_maps']} maps with BPM changes" + (f", {hit} of the notes after them as 300s" if hit else "")
            )
        lo, hi = _n(v.get("low_ar_score")), _n(v.get("high_ar_score"))
        facts.append(f"AR <8: {lo or '–'}, AR 10+: {hi or '–'}")
    elif key == "aim":
        val, ref = _n(v.get("value"), ".1f"), _n(v.get("ref"), ".1f")
        inten, combo = _n(v.get("intensity"), ".0f"), _n(v.get("combo"), ".0%")
        facts.append(f"{n:,} jumps on {v.get('maps', 0)} passed maps")
        if val:
            facts.append(
                f"cursor speed of your hardest jumps {inten} circles/s, combo held {combo} of the map; "
                f"value {val} (typical for your level {ref})"
            )
    elif key == "speed":
        bpm, best, ref = _n(v.get("bpm")), _n(v.get("best_bpm")), _n(v.get("ref_bpm"))
        clean = _n(v.get("clean_share"), ".0%")
        if bpm:
            facts.append(f"clean burst / stream speed {bpm} BPM (typical for your level {ref}), fastest map {best}")
        facts.append(f"{n:,} bursts and streams" + (f", {clean} clean" if clean else ""))
    elif key == "stamina":
        curve = v.get("curve") or {}
        if curve:
            facts.append("tempo you kept up: " + ", ".join(f"{_dur(w)} {bpm:.0f} BPM" for w, bpm in curve.items()))
        bs, stead = v.get("best_stream") or {}, _n(v.get("steadiness"), ".0%")
        if bs or stead:
            facts.append(
                (f"hardest stream {bs['notes']} notes at {bs['bpm']:.0f} BPM" if bs else "")
                + (", " if bs and stead else "")
                + (f"steadiness {stead}" if stead else "")
            )
    else:
        o, x = _n(v.get("observed")), _n(v.get("expected"))
        facts.append(f"{n:,} notes" + (f", {o} misses vs {x} expected" if o and x else ""))
    return facts


def score_text(v: dict) -> str:
    """A skill's score as shown, or why there is none."""
    s = _n(v.get("score"))
    if s:
        return s + (" · few data" if v.get("low_data") else "")
    return "too few misses to tell" if v.get("too_few_misses") else "not enough data"


def experimental_facts(skill: str, row: dict) -> list[str]:
    if skill == "consistency":
        facts = [f"{row.get('maps', 0)} analysed replays"]
        observed = num(row.get("observed_followup_misses"))
        expected_misses = num(row.get("expected_followup_misses"))
        if observed is not None and expected_misses is not None:
            facts.append(
                f"after a miss: {observed:.1f} weighted misses vs {expected_misses:.1f} expected "
                f"across {row.get('followup_notes', 0)} following notes"
            )
        chain_score = num(row.get("chain_score"))
        if chain_score is not None:
            facts.append(f"miss recovery {chain_score:.1f}/100")
        steady_score = num(row.get("steady_score"))
        spread = num(row.get("steady_spread"))
        if steady_score is not None and spread is not None:
            facts.append(
                f"between-play steadiness {steady_score:.1f}/100 "
                f"({spread:.1f} misses per 100 notes spread across {row.get('steady_plays', 0)} plays)"
            )
        if row.get("reason"):
            facts.append(str(row["reason"]))
        return facts
    facts = [f"{row.get('maps', 0)} relevant map/mod configurations"]
    measured, expected = num(row.get("measured")), num(row.get("expected"))
    if measured is not None and expected is not None:
        if skill == "accuracy":
            if row.get("hit_single_notes") is not None:
                facts.append(f"{row['hit_single_notes']:,} hit single notes")
            facts.append(f"{100 * (1 - measured):.3g}% hit as 300s")
            facts.append(
                f"non-300 rate on hit single notes (lower is better): "
                f"{100 * measured:.3g}% vs assumed {100 * expected:.3g}%"
            )
        else:
            facts.append(f"measured {measured:.3g} vs assumed reference {expected:.3g}")
    if row.get("parts"):
        facts.append("measured durations: " + ", ".join(f"{p['duration']} s" for p in row["parts"]))
    if row.get("reason"):
        facts.append(str(row["reason"]))
    return facts


# ------------------------------------------------------------------ overview
def overview(ws: Workspace, p: Profile) -> S.Overview:
    ov, lv = p.overview, p.levels
    level = num(lv.get("level_stars"))
    weights = (
        [S.LevelWeight(stars_off=float(d), weight=float(w)) for d, w in weight_table(level)[1:]]
        if level is not None
        else []
    )
    level_info = S.LevelInfo(
        stars=level,
        detected=num(lv.get("level_detected")),
        override=bool(lv.get("level_override")),
        recent_n=int(lv.get("level_recent_n") or 0),
        band=float(lv.get("level_band") or 0.5),
        sigma=float(lv.get("level_sigma") or 0.5),
        weights=weights,
        replays=len(p.replays),
        weighted_replays=float(ov.get("weighted_replays", len(p.replays))),
    )
    kpis = S.OverviewKpis(
        replays=int(ov["replays"]),
        maps=int(ov["maps"]),
        weighted_replays=float(ov.get("weighted_replays", ov["replays"])),
        play_minutes=num(ov.get("play_minutes")),
        comfort_stars=num(lv.get("comfort_stars")),
        ur=num(ov.get("ur")),
        misses_per_100=num(ov.get("misses_per_100")),
        accuracy=num(ov.get("accuracy")),
    )
    comfort_level = num(lv.get("comfort_stars")) or level
    relative_scores = {key: row.get("score") for key, row in p.experimental_skills.items()} if comfort_level else {}
    skills = [
        S.SkillScore(
            key=k,
            label=v.get("label", SKILL_LABELS.get(k, k)),
            score=num(relative_scores.get(k)),
            score_text=(p.experimental_skills.get(k) or {}).get("reason")
            if relative_scores.get(k) is None
            else f"{relative_scores[k]:.0f} · experimental comfort-relative performance",
            low_data=relative_scores.get(k) is not None and (p.experimental_skills.get(k) or {}).get("maps", 0) < 10,
            too_few_misses=False,
            n=int(v.get("n") or 0),
            facts=experimental_facts(k, p.experimental_skills.get(k) or {}),
        )
        for k, v in p.skills.items()
    ]
    rd = p.skills.get("reading") or {}
    reading_split = S.ReadingSplit(
        low_ar_score=num(rd.get("low_ar_score")),
        low_ar_maps=int(rd.get("low_ar_maps") or 0),
        high_ar_score=num(rd.get("high_ar_score")),
        high_ar_maps=int(rd.get("high_ar_maps") or 0),
    )
    few = [SKILL_LABELS.get(k, k) for k, v in p.experimental_skills.items() if v.get("score") is None]
    stam = p.skills.get("stamina") or {}
    stamina = []
    if stam.get("score") is not None and stam.get("curve"):
        ref = stam.get("ref_curve") or {}
        stamina = [
            S.StaminaPoint(seconds=float(w), bpm=float(bpm), typical=num(ref.get(w)))
            for w, bpm in stam["curve"].items()
        ]
    mb = p.miss_breakdown or {}
    total = sum(mb.values()) or 1.0
    raw = getattr(p, "miss_breakdown_raw", {}) or {}
    causes = [
        S.MissCause(cause=k, share=float(v) / total, misses=int(raw.get(k, 0)))
        for k, v in sorted(mb.items(), key=lambda kv: -kv[1])
    ]
    split = (p.aim or {}).get("split") or {}
    a, f = split.get("aim"), split.get("speed_aim")
    aim_split = None
    if a and f and a["expected"] > 0 and f["expected"] > 0:
        aim_split = S.AimSplit(fast_ratio=f["all_misses"] / f["expected"], normal_ratio=a["all_misses"] / a["expected"])
    setup = ws.setup()
    top_tips = [tip_out(t, p, setup) for t in tips(ws, p) if not t.title.endswith("fits")][:TOP_TIPS]
    return S.Overview(
        level=level_info,
        kpis=kpis,
        skills=skills,
        reading_split=reading_split,
        few_data=few,
        compare=star_compare(p),
        consistency=consistency(p),
        stamina=stamina,
        sliders_scored=relative_scores.get("sliders") is not None,
        strengths=[
            p.skills[k]["label"]
            for k in sorted(relative_scores, key=lambda k: relative_scores[k] or -1, reverse=True)
            if relative_scores[k] is not None and relative_scores[k] >= 55
        ][:3],
        weaknesses=[
            p.skills[k]["label"]
            for k in sorted(relative_scores, key=lambda k: relative_scores[k] or 101)
            if relative_scores[k] is not None and relative_scores[k] <= 45
        ][:3],
        miss_causes=causes,
        aim_split=aim_split,
        top_tips=top_tips,
        sim_exact_share=num(ov.get("sim_exact_share")),
        sim_agreement=num(ov.get("sim_agreement")),
    )


# ------------------------------------------------------------------ comparing with other star ratings, consistency
def star_compare(p: Profile) -> S.StarCompare:
    """The comfort-level scores moved to each star rating offered, with the chance to pass its maps cleanly."""
    comfort = num(p.levels.get("comfort_stars"))
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
        c = compare_at(p.experimental_skills, comfort, comfort if at_comfort else stars)
        skills = [
            S.CompareSkill(key=k, score=num(v["score"]), change=num(v["change"]), demand=num(v["demand"]))
            if v
            else S.CompareSkill(key=k, score=None, change=None, demand=None)
            for k, v in c["skills"].items()
        ]
        out.append(
            S.CompareTarget(
                stars=stars,
                comfort=at_comfort,
                locked=False,
                skills=skills,
                weakest=c["weakest"],
                pass_chance=num(c["pass_chance"]),
            )
        )
    return S.StarCompare(comfort=comfort, max_gap=MAX_GAP, targets=out, default_target=default_target(comfort))


def consistency(p: Profile) -> S.Consistency:
    return S.Consistency(
        min_plays=BAND_MIN_PLAYS,
        bands=[S.ConsistencyBand(**b) for b in consistency_bands(p.replays)],
    )


# ------------------------------------------------------------------ aim
def aim(ws: Workspace, p: Profile) -> S.AimPage:
    a, reg, wq = p.aim, p.regression, p.worst_quadrant
    kpis = S.AimKpis(
        aim_miss_share=num(a.get("aim_miss_share")),
        speed_aim_miss_share=num(a.get("speed_aim_miss_share")),
        jump_miss_rate=num(a.get("jump_miss_rate")),
        near_miss_share=num(a.get("near_miss_share")),
        jump_along_pct=num(a.get("jump_along_pct")),
    )
    worst = None
    if wq:
        worst = S.WorstQuadrant(
            quadrant=wq["quadrant"],
            miss_rate=float(wq["miss_rate"]),
            rest_miss_rate=float(wq["rest_miss_rate"]),
            relative_risk=num(wq["relative_risk"]),
            significant=bool(wq["significant"]),
        )
    q = p.quadrants
    quadrants = [
        S.QuadrantCell(
            quadrant=k,
            miss_rate=num(q.loc[k, "miss_rate"]),
            misses=float(q.loc[k, "misses"]),
            objects=float(q.loc[k, "objects"]),
        )
        for k in ("top-left", "top-right", "bottom-left", "bottom-right")
    ]
    g = ws.memo("grid", lambda: insights.playfield_grid(p))
    grid = S.PlayfieldGrid(x=g["x"], y=g["y"], rate=[nums(row) for row in g["rate"]])
    d = p.directions
    directions = [
        S.DirectionRow(
            direction=k, angle=DIR_ANGLE[k], miss_rate=num(d.loc[k, "miss_rate"]), objects=float(d.loc[k, "objects"])
        )
        for k in DIR_ANGLE
    ]
    dist = p.distances.reset_index()
    distances = [
        S.DistanceRow(
            bin=str(r["dbin"]), miss_rate=num(r["miss_rate"]), objects=float(r["objects"]), along=num(r["along"])
        )
        for r in dist.to_dict("records")
    ]
    ang = p.angles.reset_index()
    angles = [
        S.AngleRow(bin=str(r["abin"]), objects=float(r["objects"]), miss_rate=num(r["miss_rate"]))
        for r in ang.to_dict("records")
    ]
    regression = None
    if reg:
        regression = S.Regression(
            n=int(reg["n"]),
            scale_x=float(reg["scale_x"]),
            scale_y=float(reg["scale_y"]),
            rotation_deg=float(reg["rotation_deg"]),
            offset_x=float(reg["offset_x"]),
            offset_y=float(reg["offset_y"]),
        )
    return S.AimPage(
        kpis=kpis,
        worst_quadrant=worst,
        quadrants=quadrants,
        grid=grid,
        directions=directions,
        distances=distances,
        angles=angles,
        regression=regression,
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
    sp, t = p.stream_profile, p.tapping
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
    return S.StreamSpeed(rows=rows, comfort_bpm=num(t.get("comfort_bpm")), limit_bpm=num(t.get("limit_bpm")))


def _fall_behind(ws: Workspace, p: Profile) -> S.FallBehind:
    fb = getattr(p, "fall_behind", None) or {}
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
    speed = insights.fall_behind_by_speed(cb)
    curve = fb.get("curve")
    lo, hi = fb.get("practice_notes") or (None, None)
    comfort = integer(fb.get("comfort_notes"))
    comfortable_maps = practice_maps = None
    if available and comfort and lo:
        pool = ws.pool()
        if not pool.empty:
            t = targets_from_profile(p)
            easy_lo = max(9, int(comfort * 0.6))
            stamina = num((p.experimental_skills.get("stamina") or {}).get("score"))
            abilities = {"stamina": stamina} if stamina is not None else {}
            for low, high, goal in ((easy_lo, comfort, "Comfort"), (int(lo), int(hi), "Push")):
                subset = pool[(pool["max_run"] >= low) & (pool["max_run"] <= high)]
                data = recommend(
                    subset, t.comfort, abilities, "stamina", ("stamina",), min_relevance=0.0, played=t.played, targets=t
                )["goals"][goal]
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
        ur=num(t.get("ur")),
        ur_single=num(t.get("ur_single")),
        ur_streams=num(t.get("ur_streams")),
        mean_error=num(t.get("mean_error")),
        three_hundred_rate_single=num(t.get("three_hundred_rate_single")),
        alternation_in_streams=num(t.get("alternation_in_streams")),
    )
    h = ws.memo("timing", lambda: insights.timing_histogram(p))
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
    st = ws.memo("streams", lambda: insights.stream_time_series(p))
    streams = None
    if st is not None:
        streams = S.StreamsOverTime(
            bands=st["bands"],
            band_width=st["band_width"],
            notes=st["notes"],
            map=_stream_along(st["series"]["map"]),
            session=_stream_along(st["series"]["session"]),
        )
    shares = t.get("key_share") or {}
    keys = S.KeyUsage(
        shares=[S.KeyShare(key=str(k), share=float(shares[k])) for k in sorted(shares)],
        hold_ms=num(insights.key_hold_ms(p)),
        press_ms_streams=num(t.get("press_ms_streams")),
        chatter_per_1000=num(t.get("chatter_per_1000")),
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
        sliders=int(sl.get("sliders", 0) or 0),
        head_miss_rate=num(sl.get("head_miss_rate")),
        break_rate=num(sl.get("break_rate")),
        end_miss_rate=num(sl.get("end_miss_rate")),
    )
    tot = sum(p.slider_breaks.values()) or 1.0
    breaks = [
        S.BreakShare(reason=k, share=float(v) / tot) for k, v in sorted(p.slider_breaks.items(), key=lambda kv: -kv[1])
    ]
    ar = rd.get("ar_table")
    ar_misses = []
    if ar is not None and len(ar):
        ar_misses = [
            S.ArMissRow(ar=str(r["ar_bin"]), miss_rate=num(r["miss_rate"]), objects=float(r["objects"]))
            for r in ar.reset_index().to_dict("records")
        ]
    rates = ws.memo("sliders", lambda: insights.slider_rates(p)) or {}
    hits = ws.memo("hits_by_ar", lambda: insights.hits_by_ar(p))
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
        dense_miss_rate=num(rd.get("dense_miss_rate")),
        dense_threshold=num(rd.get("dense_threshold")),
        sparse_miss_rate=num(rd.get("sparse_miss_rate")),
        miss_after_miss_ratio=num(cs.get("miss_after_miss_ratio")),
        end_miss_share=num(cs.get("end_miss_share")),
        end_object_share=num(cs.get("end_object_share")),
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


def clicks(ws: Workspace, p: Profile, view: str) -> Clicks:
    return ws.memo(f"clicks:{view}", lambda: insights_service.clicks(p.objects, view))
