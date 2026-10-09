"""Aggregate many replay analyses into a player profile.

Everything here is computed from replays only:
* overview, miss breakdown (why misses happen),
* tapping (UR, bias, stream speed profile, alternation, key holds, extra taps),
* aim (spacing / direction / angle / quadrant / heat-map, over-/undershoot and an
  affine "tablet area" regression),
* sliders, reading, consistency,
* skill scores: observed vs expected misses where "expected" comes from a
  logistic model of the player's own miss chance against local difficulty
  (osu! strain model, star-equivalent per 400 ms section).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .analysis import ReplayAnalysis

QUADRANTS = ["top-left", "top-right", "bottom-left", "bottom-right"]
DIR8 = ["right", "down-right", "down", "down-left", "left", "up-left", "up", "up-right"]
SKILL_LABELS = {
    "aim": "Jump aim",
    "flow_aim": "Flow aim (spaced streams)",
    "speed": "Tapping speed (bursts/streams)",
    "stamina": "Stamina",
    "accuracy": "Accuracy (timing)",
    "sliders": "Slider control",
    "reading": "Reading (dense parts / AR)",
    "consistency": "Consistency",
}
MISS_LABELS = {
    "aim": "aim — tapped in time but outside the circle",
    "early": "too early — cursor on the note, tap outside the hit window",
    "late": "too late — cursor on the note, tap after the hit window",
    "no_tap": "no tap — cursor was on the note but no key was pressed",
    "lost": "lost — no tap and the cursor far away (didn't see / read it)",
    "notelock": "notelock — tap ignored because the previous note was still active",
}


@dataclass
class Profile:
    overview: dict
    replays: pd.DataFrame
    miss_breakdown: dict
    slider_breaks: dict
    tapping: dict
    stream_profile: pd.DataFrame
    aim: dict
    quadrants: pd.DataFrame
    worst_quadrant: dict | None
    grid: pd.DataFrame
    directions: pd.DataFrame
    distances: pd.DataFrame
    angles: pd.DataFrame
    regression: dict | None
    sliders: dict
    reading: dict
    consistency: dict
    skills: dict
    strengths: list
    weaknesses: list
    levels: dict
    objects: pd.DataFrame = field(repr=False)
    presses: pd.DataFrame = field(repr=False)


# ------------------------------------------------------------------ helpers
def _played(O: pd.DataFrame) -> pd.DataFrame:
    return O[(O["played"]) & (O["kind"] != "spinner")]


def _rate(miss: pd.Series) -> float:
    return float(miss.mean()) if len(miss) else math.nan


def _ur(errs: pd.Series) -> float:
    errs = errs.dropna()
    return float(10 * errs.std(ddof=0)) if len(errs) > 5 else math.nan


def _clip(v, lo=0.0, hi=100.0):
    return float(min(hi, max(lo, v)))


def _score_from_ratio(expected: float, observed: float) -> float:
    """50 = as expected, each halving of misses vs expectation = +35."""
    expected = max(expected, 1e-6)
    observed = max(observed, 0.5)  # Laplace-ish floor, avoids infinite scores
    return _clip(50 + 35 * math.log2(expected / observed))


# ------------------------------------------------------------------ aim
def quadrant_stats(O: pd.DataFrame) -> pd.DataFrame:
    P = _played(O)
    rows = []
    for q in QUADRANTS:
        d = P[P["quadrant"] == q]
        miss = ~d["head_hit"]
        aim_rows = d[d["head_hit"] | (d["miss_reason"] == "aim")]
        rows.append({
            "quadrant": q, "objects": len(d), "misses": int(miss.sum()), "miss_rate": _rate(miss),
            "aim_misses": int((d["miss_reason"] == "aim").sum()),
            "aim_miss_rate": _rate(d["miss_reason"] == "aim"),
            "mean_dx": float(aim_rows["err_dx"].mean()) if len(aim_rows) else math.nan,
            "mean_dy": float(aim_rows["err_dy"].mean()) if len(aim_rows) else math.nan,
            "along": float(d["along"].mean()) if "along" in d and d["along"].notna().any() else math.nan,
        })
    return pd.DataFrame(rows).set_index("quadrant")


def worst_quadrant(q: pd.DataFrame) -> dict | None:
    q = q[q["objects"] > 0]
    if q.empty or q["misses"].sum() == 0:
        return None
    name = q["miss_rate"].idxmax()
    row = q.loc[name]
    rest = q.drop(index=name)
    n1, m1 = row["objects"], row["misses"]
    n2, m2 = rest["objects"].sum(), rest["misses"].sum()
    p1 = m1 / n1
    p2 = m2 / n2 if n2 else 0.0
    pooled = (m1 + m2) / (n1 + n2)
    se = math.sqrt(max(pooled * (1 - pooled) * (1 / n1 + 1 / max(n2, 1)), 1e-12))
    z = (p1 - p2) / se
    rr = p1 / p2 if p2 > 0 else math.inf
    return {"quadrant": name, "miss_rate": float(p1), "rest_miss_rate": float(p2), "relative_risk": float(rr),
            "z": float(z), "objects": int(n1), "misses": int(m1),
            "mean_dx": float(row["mean_dx"]), "mean_dy": float(row["mean_dy"]), "along": float(row["along"]),
            "aim_miss_rate": float(row["aim_miss_rate"]),
            "significant": bool(z > 2.0 and n1 >= 80 and m1 >= 8 and rr >= 1.25)}


def grid_stats(O: pd.DataFrame) -> pd.DataFrame:
    P = _played(O)
    g = P.groupby("grid").agg(objects=("head_hit", "size"), misses=("head_hit", lambda s: int((~s).sum())))
    g["miss_rate"] = g["misses"] / g["objects"]
    return g.reindex(range(9)).fillna({"objects": 0, "misses": 0})


def direction_stats(O: pd.DataFrame) -> pd.DataFrame:
    P = _played(O)
    P = P[P["dist_norm"] >= 1.0]
    rows = []
    for d in DIR8:
        s = P[P["dir8"] == d]
        rows.append({"direction": d, "objects": len(s), "miss_rate": _rate(~s["head_hit"]),
                     "aim_miss_rate": _rate(s["miss_reason"] == "aim"),
                     "along": float(s["along"].mean()) if len(s) else math.nan,
                     "cross": float(s["cross"].mean()) if len(s) else math.nan})
    return pd.DataFrame(rows).set_index("direction")


def distance_stats(O: pd.DataFrame) -> pd.DataFrame:
    P = _played(O).dropna(subset=["dist_norm"])
    bins = [0, 0.5, 1, 1.5, 2, 3, 4, 100]
    labels = ["<0.5", "0.5-1", "1-1.5", "1.5-2", "2-3", "3-4", "4+"]
    P = P.assign(dbin=pd.cut(P["dist_norm"], bins=bins, labels=labels, right=False))
    g = P.groupby("dbin", observed=False).agg(objects=("head_hit", "size"),
                                              miss_rate=("head_hit", lambda s: float((~s).mean()) if len(s) else np.nan),
                                              along=("along", "mean"),
                                              aim_err=("aim_err", "median"))
    return g


def angle_stats(O: pd.DataFrame) -> pd.DataFrame:
    P = _played(O).dropna(subset=["angle"])
    P = P[P["dist_norm"] >= 1.0]
    P = P.assign(abin=pd.cut(P["angle"], bins=[0, 60, 120, 181], labels=["sharp (<60°)", "medium", "wide (>120°)"],
                             right=False))
    return P.groupby("abin", observed=False).agg(objects=("head_hit", "size"),
                                                 miss_rate=("head_hit", lambda s: float((~s).mean()) if len(s) else np.nan),
                                                 along=("along", "mean"))


def aim_regression(O: pd.DataFrame, min_dist_norm: float = 1.5) -> dict | None:
    """Fit actual movement = M * intended movement + b on jumps.

    M is decomposed into rotation R and stretch S (polar decomposition):
    scale_x/scale_y > 1 = moving too far (overaim) horizontally/vertically,
    rotation_deg > 0 = clockwise on screen; b = constant offset (px)."""
    P = _played(O)
    usable = P["head_hit"] | (P["miss_reason"] == "aim")
    d = P[usable & (P["dist_norm"] >= min_dist_norm)].dropna(subset=["start_x", "start_y", "err_dx", "err_dy"])
    if len(d) < 40:
        return None
    ix = (d["x"] - d["start_x"]).to_numpy()
    iy = (d["y"] - d["start_y"]).to_numpy()
    ex = d["err_dx"].to_numpy()
    ey = d["err_dy"].to_numpy()
    X = np.column_stack([ix, iy, np.ones(len(d))])
    cx, res_x, *_ = np.linalg.lstsq(X, ex, rcond=None)
    cy, res_y, *_ = np.linalg.lstsq(X, ey, rcond=None)
    M = np.array([[1 + cx[0], cx[1]], [cy[0], 1 + cy[1]]])
    U, sig, Vt = np.linalg.svd(M)
    R = U @ Vt
    if np.linalg.det(R) < 0:  # reflection guard
        U[:, -1] *= -1
        R = U @ Vt
    S = Vt.T @ np.diag(sig) @ Vt
    rot = math.degrees(math.atan2(R[1, 0], R[0, 0]))
    resid_x = ex - X @ cx
    resid_y = ey - X @ cy
    n = len(d)
    se_off = math.sqrt((resid_x.var() + resid_y.var()) / 2 / n)
    radius = float(d["radius"].median()) if "radius" in d else 36.5
    return {"n": n, "scale_x": float(S[0, 0]), "scale_y": float(S[1, 1]), "rotation_deg": rot,
            "offset_x": float(cx[2]), "offset_y": float(cy[2]), "offset_se": se_off,
            "residual_px": float(math.sqrt((resid_x.var() + resid_y.var()) / 2)), "radius": radius}


# ------------------------------------------------------------------ tapping
STREAM_PROFILE_COLUMNS = ["bpm_bin", "objects", "miss_rate", "non300_rate", "ur", "mean_err"]


def stream_speed_profile(O: pd.DataFrame, min_objects: int = 20, min_run: int = 7) -> pd.DataFrame:
    """Miss rate / UR by stream speed (1/4-note BPM, real time). Short bursts are
    left out (min_run): 3-note triplets at 300 BPM say nothing about streaming."""
    P = _played(O)
    S = P[(P["run_len"] >= min_run) & (P["run_pos"] >= 1)].dropna(subset=["stream_bpm"])
    S = S[np.isfinite(S["stream_bpm"].astype(float))]
    if S.empty:
        return pd.DataFrame(columns=STREAM_PROFILE_COLUMNS)
    S = S.assign(bpm_bin=(S["stream_bpm"] // 10 * 10).astype(int))
    rows = []
    for b, d in S.groupby("bpm_bin"):
        if len(d) < min_objects:
            continue
        hits = d[d["head_hit"]]
        rows.append({"bpm_bin": int(b), "objects": len(d), "miss_rate": _rate(~d["head_hit"]),
                     "non300_rate": _rate(hits["head_result"] != 300) if len(hits) else math.nan,
                     "ur": _ur(hits["err_real"]), "mean_err": float(hits["err_real"].mean()) if len(hits) else math.nan})
    if not rows:
        return pd.DataFrame(columns=STREAM_PROFILE_COLUMNS)
    return pd.DataFrame(rows).sort_values("bpm_bin").reset_index(drop=True)


def stream_limits(prof: pd.DataFrame, base_ur: float) -> dict:
    out = {"comfort_bpm": None, "limit_bpm": None}
    if prof is None or prof.empty:
        return out
    good = prof[(prof["objects"] >= 40) & (prof["miss_rate"] <= 0.03)
                & ((prof["ur"] <= 1.6 * base_ur) | np.isnan(base_ur))]
    if not good.empty:
        out["comfort_bpm"] = int(good["bpm_bin"].max())
    above = prof[(prof["objects"] >= 30) & (prof["miss_rate"] >= 0.08)]
    if out["comfort_bpm"] is not None:
        above = above[above["bpm_bin"] > out["comfort_bpm"]]
    if not above.empty:
        out["limit_bpm"] = int(above["bpm_bin"].min())
    return out


def stream_drift(O: pd.DataFrame) -> dict:
    """Timing error vs position inside long runs: +ms per note = falling behind."""
    P = _played(O)
    S = P[(P["run_len"] >= 8) & P["head_hit"]].dropna(subset=["err_real"])
    if len(S) < 60:
        return {"slope_ms_per_note": math.nan, "late_half_err": math.nan, "early_half_err": math.nan, "n": len(S)}
    slope = np.polyfit(S["run_pos"].to_numpy(dtype=float), S["err_real"].to_numpy(dtype=float), 1)[0]
    half = S["run_pos"] >= S["run_len"] / 2
    return {"slope_ms_per_note": float(slope), "late_half_err": float(S.loc[half, "err_real"].mean()),
            "early_half_err": float(S.loc[~half, "err_real"].mean()), "n": len(S)}


def tapping_metrics(O: pd.DataFrame, Pr: pd.DataFrame, rates: dict) -> dict:
    P = _played(O)
    hits = P[P["head_hit"]]
    single = hits[hits["run_len"] < 3]
    runs = hits[hits["run_len"] >= 3]
    errs = hits["err_real"].dropna()
    out = {
        "ur": _ur(hits["err_real"]), "ur_single": _ur(single["err_real"]), "ur_streams": _ur(runs["err_real"]),
        "mean_error": float(errs.mean()) if len(errs) else math.nan,
        "early_share": float((errs < 0).mean()) if len(errs) else math.nan,
        "three_hundred_rate_single": _rate(single["head_result"] == 300),
        "timing_miss_share": math.nan,
    }
    misses = P[~P["head_hit"]]
    if len(misses):
        out["timing_miss_share"] = float(misses["miss_reason"].isin(["early", "late"]).mean())
    out.update(stream_drift(O))
    if Pr is None or Pr.empty:
        return out
    Pr = Pr.copy()
    Pr["rate"] = Pr["replay_key"].map(rates).fillna(1.0)
    Pr["duration_real"] = Pr["duration"] / Pr["rate"]
    total = len(Pr)
    keys = Pr["key"].value_counts()
    out["key_share"] = {k: float(v / total) for k, v in keys.items()}
    # lazer replays only record left/right ("L"/"R"), not whether a key or a mouse/pen button was used
    legacy = Pr[Pr["key"].isin(["K1", "K2", "M1", "M2"])]
    out["mouse_button_share"] = float(legacy["key"].isin(["M1", "M2"]).mean()) if len(legacy) >= 200 else math.nan
    out["key_device_known_share"] = float(len(legacy) / total) if total else math.nan
    in_run = Pr[(Pr["target_run_len"] >= 3)]
    out["alternation_in_streams"] = float(in_run["alternated"].mean()) if len(in_run) > 30 else math.nan
    half = Pr[(Pr["target_pattern"].isin(["jump", "single", "spaced"])) & (Pr["gap_prev"] < 400)]
    out["alternation_singles"] = float(half["alternated"].mean()) if len(half) > 30 else math.nan
    out["press_ms_median"] = float(Pr["duration_real"].median())
    out["press_ms_streams"] = float(in_run["duration"].div(in_run["rate"]).median()) if len(in_run) else math.nan
    out["hold_ratio_streams"] = float(in_run["hold_ratio"].median()) if len(in_run) > 30 else math.nan
    # overlapping holds in streams: the other key still down when the next press lands
    out["overlap_in_streams"] = math.nan
    if len(in_run) > 30:
        nxt_gap = Pr["time"].shift(-1) - Pr["time"]
        overlap = (Pr["duration"] > nxt_gap) & (Pr["target_run_len"] >= 3)
        out["overlap_in_streams"] = float(overlap[Pr["target_run_len"] >= 3].mean())
    # very quick re-press of the same key after releasing it (chatter / double taps)
    out["chatter_per_1000"] = float((Pr["same_key_gap"] <= 20).sum() / max(total, 1) * 1000)
    # presses that hit nothing while notes were due (overtapping); exclude slider/spinner bodies
    out["extra_presses_per_100"] = _extra_presses(O, Pr)
    out["press_count"] = total
    return out


def _extra_presses(O: pd.DataFrame, Pr: pd.DataFrame) -> float:
    count = 0
    n_obj = 0
    for key, objs in O.groupby("replay_key"):
        pr = Pr[(Pr["replay_key"] == key) & (Pr["outcome"] == "none")]
        objs = objs[objs["kind"] != "spinner"]
        n_obj += int(objs["played"].sum())
        if pr.empty or objs.empty:
            continue
        starts = objs["time"].to_numpy()
        bodies = objs[objs["kind"] == "slider"][["time", "end_time"]].to_numpy()
        spinners = O[(O["replay_key"] == key) & (O["kind"] == "spinner")][["time", "end_time"]].to_numpy()
        for t in pr["time"].to_numpy():
            j = np.searchsorted(starts, t)
            near = min(abs(t - starts[j]) if j < len(starts) else 1e9, abs(t - starts[j - 1]) if j > 0 else 1e9)
            if near > 150:
                continue
            if len(bodies) and np.any((bodies[:, 0] < t) & (t <= bodies[:, 1])):
                continue
            if len(spinners) and np.any((spinners[:, 0] <= t) & (t <= spinners[:, 1])):
                continue
            count += 1
    return float(count / max(n_obj, 1) * 100)


# ------------------------------------------------------------------ expectation model
def fit_miss_model(df: pd.DataFrame, col: str = "local_eq"):
    """Logistic regression P(miss) = s(a + b*eq); returns predict(eq_array)."""
    d = df.dropna(subset=[col])
    y = (~d["head_hit"].astype(bool)).to_numpy(dtype=float)
    x = d[col].to_numpy(dtype=float)
    base = float(y.mean()) if len(y) else 0.05
    if len(d) < 50 or y.sum() < 3 or y.sum() > len(y) - 3:
        return lambda e: np.full(np.shape(e), base)
    mu, sd = x.mean(), x.std() or 1.0
    z = (x - mu) / sd
    X = np.column_stack([np.ones_like(z), z])
    w = np.array([math.log(max(base, 1e-3) / max(1 - base, 1e-3)), 0.0])
    lam = 1e-3
    for _ in range(50):
        p = _sigmoid(X @ w)
        g = X.T @ (p - y) + lam * w
        H = X.T @ (X * (p * (1 - p))[:, None]) + lam * np.eye(2)
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break

    def predict(e):
        e = (np.asarray(e, dtype=float) - mu) / sd
        return _sigmoid(w[0] + w[1] * e)

    predict.coef = (w[0], w[1], mu, sd)  # type: ignore[attr-defined]
    return predict


def _sigmoid(z):
    # clipped: extreme difficulty values must not overflow exp() (p is ~0 or ~1 there anyway)
    return 1 / (1 + np.exp(-np.clip(z, -35.0, 35.0)))


def _local_eq(O: pd.DataFrame) -> pd.Series:
    a = O["aim_eq"] if "aim_eq" in O else pd.Series(np.nan, index=O.index)
    s = O["speed_eq"] if "speed_eq" in O else pd.Series(np.nan, index=O.index)
    eq = pd.concat([a, s], axis=1).max(axis=1)
    if "stars" in O:
        eq = eq.fillna(O["stars"])
    return eq


# ------------------------------------------------------------------ build
def build_profile(analyses: list[ReplayAnalysis]) -> Profile:
    metas = pd.DataFrame([a.meta for a in analyses])
    objs = []
    for a in analyses:
        o = a.objects.copy()
        o["stars"] = a.meta.get("stars", np.nan)
        o["map_ar"] = a.meta.get("ar", np.nan)
        o["rate"] = a.meta.get("rate", 1.0)
        o["date"] = a.meta.get("date")
        o["hidden"] = bool(a.meta.get("mods", 0) & 8)
        objs.append(o)
    O = pd.concat(objs, ignore_index=True) if objs else pd.DataFrame()
    Pr = pd.concat([a.presses for a in analyses], ignore_index=True) if analyses else pd.DataFrame()
    rates = {a.key: a.meta.get("rate", 1.0) for a in analyses}
    O["local_eq"] = _local_eq(O)
    P = _played(O)
    misses = P[~P["head_hit"]]

    overview = {
        "replays": len(analyses), "maps": int(metas["beatmap_md5"].nunique()) if len(metas) else 0,
        "objects": len(P), "head_misses": int(len(misses)), "miss_rate": _rate(~P["head_hit"]),
        "misses_per_100": 100 * _rate(~P["head_hit"]),
        "accuracy": float(metas["accuracy"].mean()) if len(metas) else math.nan,
        "avg_stars": float(np.average(metas["stars"].fillna(0), weights=metas["n_objects"])) if "stars" in metas and len(metas) else math.nan,
        "max_stars_passed": float(metas.loc[metas["completed"], "stars"].max()) if "stars" in metas and metas["completed"].any() else math.nan,
        "ur": _ur(P.loc[P["head_hit"], "err_real"]),
        "sim_exact_share": float(metas["sim_match"].dropna().astype(float).mean()) if len(metas) else math.nan,
        "sim_agreement": float(pd.to_numeric(metas["sim_agreement"], errors="coerce").mean()) if len(metas) else math.nan,
        "play_minutes": float(metas["length_s"].sum() / 60) if "length_s" in metas else math.nan,
        "first_date": metas["date"].min() if len(metas) else None, "last_date": metas["date"].max() if len(metas) else None,
    }
    miss_breakdown = misses["miss_reason"].fillna("lost").value_counts().to_dict()
    sliders_all = P[P["kind"] == "slider"]
    broke = sliders_all[sliders_all["broke"] == True]  # noqa: E712
    slider_breaks = broke["break_reason"].fillna("follow").value_counts().to_dict()

    tapping = tapping_metrics(O, Pr, rates)
    sprof = stream_speed_profile(O)
    tapping.update(stream_limits(sprof, tapping.get("ur_single", math.nan)))

    q = quadrant_stats(O)
    wq = worst_quadrant(q)
    reg = aim_regression(O)
    jumps = P[P["pattern"].isin(["jump", "spaced"])]
    aim = {
        "aim_miss_rate": _rate(P["miss_reason"] == "aim"),
        "aim_miss_share": float((misses["miss_reason"] == "aim").mean()) if len(misses) else math.nan,
        "near_miss_share": float((misses["miss_dist"] <= 1.4).mean()) if len(misses) else math.nan,
        "jump_objects": len(jumps), "jump_miss_rate": _rate(~jumps["head_hit"]),
        "jump_along": float(jumps["along"].mean()) if len(jumps) else math.nan,
        "jump_along_pct": float((jumps["along"] * jumps["radius"] / jumps["dist"]).median() * 100) if len(jumps) else math.nan,
        "aim_err_median": float(P.loc[P["head_hit"], "aim_err"].median()) if len(P) else math.nan,
        "after_slider_miss_rate": _rate(~P.loc[P["from_slider"] == True, "head_hit"]),  # noqa: E712
        "spaced_stream_objects": int(P["spaced_stream"].sum()),
        "spaced_stream_miss_rate": _rate(~P.loc[P["spaced_stream"], "head_hit"]),
    }
    slider_metrics = {
        "sliders": len(sliders_all),
        "head_miss_rate": _rate(~sliders_all["head_hit"]),
        "break_rate": float(len(broke) / max(int(sliders_all["head_hit"].sum()), 1)),
        "end_miss_rate": _rate(sliders_all.loc[sliders_all["head_hit"], "end_hit"] == False),  # noqa: E712
    }
    reading = _reading_metrics(P, misses)
    consistency = _consistency_metrics(P, metas)
    model = fit_miss_model(P.assign(local_eq=P["local_eq"]))
    reading.update(_reading_ratios(P, model))
    skills = _skills(P, model, tapping, slider_metrics, reading, consistency)
    strengths, weaknesses = _rank_skills(skills)
    levels = _levels(metas, P, model)
    return Profile(overview=overview, replays=metas, miss_breakdown=miss_breakdown, slider_breaks=slider_breaks,
                   tapping=tapping, stream_profile=sprof, aim=aim, quadrants=q, worst_quadrant=wq,
                   grid=grid_stats(O), directions=direction_stats(O), distances=distance_stats(O),
                   angles=angle_stats(O), regression=reg, sliders=slider_metrics, reading=reading,
                   consistency=consistency, skills=skills, strengths=strengths, weaknesses=weaknesses,
                   levels=levels, objects=O, presses=Pr)


def _reading_metrics(P: pd.DataFrame, misses: pd.DataFrame) -> dict:
    out = {"lost_share": float((misses["miss_reason"] == "lost").mean()) if len(misses) else math.nan}
    if len(P):
        hi = P["density"] >= max(4, P["density"].quantile(0.8))
        out["dense_miss_rate"] = _rate(~P.loc[hi, "head_hit"])
        out["sparse_miss_rate"] = _rate(~P.loc[~hi, "head_hit"])
        out["dense_threshold"] = float(max(4, P["density"].quantile(0.8)))
        ar = P["map_ar"]
        out["high_ar_miss_rate"] = _rate(~P.loc[ar >= 9.5, "head_hit"]) if (ar >= 9.5).sum() > 50 else math.nan
        out["low_ar_miss_rate"] = _rate(~P.loc[ar <= 7, "head_hit"]) if (ar <= 7).sum() > 50 else math.nan
        out["mid_ar_miss_rate"] = _rate(~P.loc[(ar > 7) & (ar < 9.5), "head_hit"])
        out["hidden_miss_rate"] = _rate(~P.loc[P["hidden"], "head_hit"]) if P["hidden"].sum() > 50 else math.nan
        out["ar_table"] = (P.assign(ar_bin=(ar * 2).round() / 2).groupby("ar_bin")
                           .agg(objects=("head_hit", "size"), miss_rate=("head_hit", lambda s: float((~s).mean())))
                           .query("objects >= 30"))
    return out


def _reading_ratios(P: pd.DataFrame, model) -> dict:
    """Observed / expected misses (the player's own difficulty model) for reading-related
    subsets. Raw miss rates by AR or note density mostly measure that high-AR / dense maps
    are harder; these ratios ask whether you miss *more than their difficulty explains*."""
    out = {}
    if P.empty:
        return out

    def ratio(mask) -> tuple[float, int, float]:
        d = P[mask]
        if len(d) < 150:
            return math.nan, len(d), math.nan
        exp = float(np.nansum(model(d["local_eq"].to_numpy())))
        obs = float((~d["head_hit"]).sum())
        return (obs / exp if exp >= 5 else math.nan), len(d), obs

    ar = P["map_ar"]
    for name, mask in (("high_ar", ar >= 9.5), ("mid_ar", (ar > 7) & (ar < 9.5)), ("low_ar", ar <= 7)):
        out[f"{name}_ratio"], out[f"{name}_n"], out[f"{name}_misses"] = ratio(mask)
    thr = max(4, P["density"].quantile(0.8))
    out["dense_ratio"], out["dense_n"], out["dense_misses"] = ratio(P["density"] >= thr)
    out["sparse_ratio"], out["sparse_n"], _ = ratio(P["density"] < thr)
    return out


def miss_chain_ratio(P: pd.DataFrame, window: int = 10) -> float:
    """Do misses make more misses? Observed / expected misses on the `window`
    notes after a miss, where "expected" comes from the player's own
    difficulty->miss model. Misses cluster in hard sections anyway; this ratio
    only rises above ~1 when a miss itself throws the player off (tilt, losing
    the rhythm). Notelock follow-ups are mechanical, so they are ignored."""
    if P.empty or "local_eq" not in P:
        return math.nan
    parts = []
    for _, d in P.groupby("replay_key", sort=False):
        is_nl = ((d["miss_reason"] == "notelock") & ~d["head_hit"].astype(bool)).to_numpy()
        prim = (~d["head_hit"].astype(bool)).to_numpy() & ~is_nl
        recent = pd.Series(prim.astype(float)).rolling(window, min_periods=1).max().shift(1).fillna(0).to_numpy()
        parts.append(pd.DataFrame({"local_eq": d["local_eq"].to_numpy(), "head_hit": ~prim,
                                   "after": recent > 0, "skip": is_nl}))
    if not parts:
        return math.nan
    D = pd.concat(parts, ignore_index=True)
    D = D[~D["skip"]]
    fresh, after = D[~D["after"]], D[D["after"]]
    if len(after) < 20 or len(fresh) < 50:
        return math.nan
    # expectation from notes with no recent miss, at the same local difficulty
    model = fit_miss_model(fresh)
    exp = float(np.nansum(model(after["local_eq"].to_numpy())))
    obs = float((~after["head_hit"]).sum())
    if exp <= 0:
        return math.nan
    # shrink towards the typical value (~2x, median of real replays) so a handful of
    # misses can't produce extreme ratios: prior worth 5 expected misses
    return (obs + 5 * TYPICAL_CHAIN_RATIO) / (exp + 5)


TYPICAL_CHAIN_RATIO = 2.0


def _consistency_metrics(P: pd.DataFrame, metas: pd.DataFrame) -> dict:
    out = {}
    if P.empty:
        return out
    out["miss_after_miss_ratio"] = miss_chain_ratio(P)
    end = P["time_frac"] >= 0.8
    out["end_miss_share"] = float((~P.loc[end, "head_hit"]).sum() / max((~P["head_hit"]).sum(), 1))
    out["end_object_share"] = float(end.mean())
    first, second = P["time_frac"] < 0.5, P["time_frac"] >= 0.5
    out["first_half_miss_rate"] = _rate(~P.loc[first, "head_hit"])
    out["second_half_miss_rate"] = _rate(~P.loc[second, "head_hit"])
    if len(metas) >= 3:
        out["accuracy_std"] = float(metas["accuracy"].std())
    return out


def _subset_score(P: pd.DataFrame, mask: pd.Series, model, min_n: int = 60) -> dict:
    d = P[mask]
    n = len(d)
    obs = float((~d["head_hit"]).sum())
    if n == 0:
        return {"score": None, "n": 0, "observed": 0, "expected": 0}
    exp = float(np.nansum(model(d["local_eq"].to_numpy())))
    score = _score_from_ratio(exp, obs) if (n >= min_n and exp >= 3) else None
    return {"score": score, "n": n, "observed": obs, "expected": exp,
            "miss_rate": obs / n, "ratio": obs / exp if exp > 0 else math.nan}


def _skills(P, model, tapping, sliders, reading, consistency) -> dict:
    s = {}
    s["aim"] = _subset_score(P, P["pattern"].isin(["jump", "spaced"]), model)
    s["flow_aim"] = _subset_score(P, P["spaced_stream"].astype(bool), model)
    s["speed"] = _subset_score(P, P["pattern"].isin(["burst", "stream"]), model)
    # stamina: late part of long runs vs early part of the same runs
    long_runs = P[P["run_len"] >= 16]
    if len(long_runs) >= 80:
        late = long_runs["run_pos"] >= long_runs["run_len"] / 2
        e_rate = _rate(~long_runs.loc[~late, "head_hit"])
        l_rate = _rate(~long_runs.loc[late, "head_hit"])
        n_late = int(late.sum())
        score = _score_from_ratio(e_rate * n_late, l_rate * n_late) if e_rate > 0 or l_rate > 0 else 75.0
        s["stamina"] = {"score": score, "n": len(long_runs), "early_miss_rate": e_rate, "late_miss_rate": l_rate}
    else:
        s["stamina"] = {"score": None, "n": len(long_runs)}
    r300 = tapping.get("three_hundred_rate_single", math.nan)
    n_single = int((P["run_len"] < 3).sum())
    s["accuracy"] = {"score": _clip((r300 - 0.5) / 0.45 * 100) if not math.isnan(r300) and n_single >= 60 else None,
                     "n": n_single, "three_hundred_rate": r300, "ur": tapping.get("ur_single")}
    br = sliders.get("break_rate", math.nan)
    n_sl = sliders.get("sliders", 0)
    s["sliders"] = {"score": _clip(100 - br * 400) if n_sl >= 30 and not math.isnan(br) else None, "n": n_sl,
                    "break_rate": br}
    if "dense_threshold" in reading:
        s["reading"] = _subset_score(P, P["density"] >= reading["dense_threshold"], model)
    else:
        s["reading"] = {"score": None, "n": 0}
    ratio = consistency.get("miss_after_miss_ratio", math.nan)
    s["consistency"] = {"score": _clip(50 + 30 * math.log2(TYPICAL_CHAIN_RATIO / ratio))
                        if ratio and not math.isnan(ratio) else None,
                        "n": len(P), "miss_after_miss_ratio": ratio}
    for k, v in s.items():
        v["label"] = SKILL_LABELS[k]
    return s


def _rank_skills(skills: dict) -> tuple[list, list]:
    scored = [(k, v["score"]) for k, v in skills.items() if v.get("score") is not None]
    scored.sort(key=lambda kv: kv[1], reverse=True)
    strengths = [k for k, sc in scored[:3] if sc >= 55]
    weaknesses = [k for k, sc in sorted(scored, key=lambda kv: kv[1])[:3] if sc <= 45]
    if not weaknesses and len(scored) >= 3:
        weaknesses = [scored[-1][0]]  # always give one thing to work on
    return strengths, weaknesses


def _levels(metas: pd.DataFrame, P: pd.DataFrame, model) -> dict:
    """Difficulty levels (star rating units) used to pick practice maps."""
    out = {"comfort_stars": math.nan, "aim_level": math.nan, "speed_level": math.nan}
    if metas.empty or "stars" not in metas:
        return out
    m = metas.dropna(subset=["stars"])
    m = m.assign(miss_per_100=m["head_misses"] / m["n_objects"].clip(lower=1) * 100)
    good = m[(m["miss_per_100"] <= 2.0) & (m["completed"])]
    if len(good):
        out["comfort_stars"] = float(good["stars"].quantile(0.75))
    else:
        out["comfort_stars"] = float(m["stars"].quantile(0.25) - 0.4)
    # skill levels: local star-equivalent where predicted miss chance reaches 5%
    coef = getattr(model, "coef", None)
    for skill, col in (("aim_level", "aim_eq"), ("speed_level", "speed_eq")):
        d = P.dropna(subset=[col])
        if len(d) < 300:
            continue
        bins = np.arange(0, d[col].max() + 0.25, 0.25)
        d = d.assign(b=pd.cut(d[col], bins=bins, labels=bins[:-1]))
        g = d.groupby("b", observed=True)["head_hit"].agg(["size", lambda s: float((~s).mean())])
        g.columns = ["n", "miss"]
        g = g[g["n"] >= 40]
        ok = g[g["miss"] <= 0.05]
        if len(ok):
            out[skill] = float(ok.index.max()) + 0.25
    out["model_coef"] = coef
    return out
