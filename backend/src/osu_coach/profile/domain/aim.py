"""Aim: quadrants, directions, distances, angles, click points, the tablet-area regression; jump aim and flow aim scores."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from osu_coach.profile.domain.constants import DIR8, QUADRANTS
from osu_coach.profile.domain.misses import fast_pattern
from osu_coach.profile.domain.ranking import _n_replays, rank_weights, ranked_mean
from osu_coach.profile.domain.stats import _clip, _map_key, _rate, _w, _wmean, _wquantile, _wstd, played_notes


def quadrant_stats(O: pd.DataFrame) -> pd.DataFrame:
    P = played_notes(O)
    rows = []
    for q in QUADRANTS:
        d = P[P["quadrant"] == q]
        w = _w(d)
        miss = ~d["head_hit"]
        aim = d["miss_reason"] == "aim"
        aim_rows = d[d["head_hit"] | aim]
        aw = _w(aim_rows)
        rows.append(
            {
                "quadrant": q,
                "objects": float(w.sum()),
                "misses": float((miss * w).sum()),
                "miss_rate": _rate(miss, w),
                "aim_misses": float((aim * w).sum()),
                "aim_miss_rate": _rate(aim, w),
                "mean_dx": _wmean(aim_rows["err_dx"], aw) if len(aim_rows) else math.nan,
                "mean_dy": _wmean(aim_rows["err_dy"], aw) if len(aim_rows) else math.nan,
                "along": _wmean(d["along"], w) if "along" in d and d["along"].notna().any() else math.nan,
            }
        )
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
    return {
        "quadrant": name,
        "miss_rate": float(p1),
        "rest_miss_rate": float(p2),
        "relative_risk": float(rr),
        "z": float(z),
        "objects": int(round(n1)),
        "misses": int(round(m1)),
        "mean_dx": float(row["mean_dx"]),
        "mean_dy": float(row["mean_dy"]),
        "along": float(row["along"]),
        "aim_miss_rate": float(row["aim_miss_rate"]),
        "significant": bool(z > 2.0 and n1 >= 80 and m1 >= 8 and rr >= 1.25),
    }


def grid_stats(O: pd.DataFrame) -> pd.DataFrame:
    P = played_notes(O)
    P = P.assign(_w=_w(P), _m=(~P["head_hit"]).astype(float) * _w(P))
    g = P.groupby("grid").agg(objects=("_w", "sum"), misses=("_m", "sum"))
    g["miss_rate"] = g["misses"] / g["objects"]
    return g.reindex(range(9)).fillna({"objects": 0, "misses": 0})


def direction_stats(O: pd.DataFrame) -> pd.DataFrame:
    P = played_notes(O)
    P = P[P["dist_norm"] >= 1.0]
    rows = []
    for d in DIR8:
        s = P[P["dir8"] == d]
        w = _w(s)
        rows.append(
            {
                "direction": d,
                "objects": float(w.sum()),
                "miss_rate": _rate(~s["head_hit"], w),
                "aim_miss_rate": _rate(s["miss_reason"] == "aim", w),
                "along": _wmean(s["along"], w) if len(s) else math.nan,
                "cross": _wmean(s["cross"], w) if len(s) else math.nan,
            }
        )
    return pd.DataFrame(rows).set_index("direction")


def _wgroup(P: pd.DataFrame, by: str, aim_err: bool = False) -> pd.DataFrame:
    """Weighted objects / miss rate / mean over-undershoot (``along``) per group."""
    w = _w(P)
    has = P["along"].notna()
    D = P.assign(_w=w, _m=(~P["head_hit"]).astype(float) * w, _a=P["along"].fillna(0.0) * w, _aw=w.where(has, 0.0))
    g = D.groupby(by, observed=False).agg(
        objects=("_w", "sum"), misses=("_m", "sum"), _a=("_a", "sum"), _aw=("_aw", "sum")
    )
    g["miss_rate"] = (g["misses"] / g["objects"]).where(g["objects"] > 0)
    g["along"] = (g["_a"] / g["_aw"]).where(g["_aw"] > 0)
    g = g.drop(columns=["_a", "_aw", "misses"])
    if aim_err:
        g["aim_err"] = P.groupby(by, observed=False)["aim_err"].median()
    return g


def distance_stats(O: pd.DataFrame) -> pd.DataFrame:
    P = played_notes(O).dropna(subset=["dist_norm"])
    bins = [0, 0.5, 1, 1.5, 2, 3, 4, 100]
    labels = ["<0.5", "0.5-1", "1-1.5", "1.5-2", "2-3", "3-4", "4+"]
    P = P.assign(dbin=pd.cut(P["dist_norm"], bins=bins, labels=labels, right=False))
    return _wgroup(P, "dbin", aim_err=True)


def angle_stats(O: pd.DataFrame) -> pd.DataFrame:
    P = played_notes(O).dropna(subset=["angle"])
    P = P[P["dist_norm"] >= 1.0]
    P = P.assign(
        abin=pd.cut(P["angle"], bins=[0, 60, 120, 181], labels=["sharp (<60°)", "medium", "wide (>120°)"], right=False)
    )
    return _wgroup(P, "abin")


def aim_regression(O: pd.DataFrame, min_dist_norm: float = 1.5) -> dict | None:
    """Fit actual movement = M * intended movement + b on jumps (weighted least squares).

    M is decomposed into rotation R and stretch S (polar decomposition):
    scale_x/scale_y > 1 = moving too far (overaim) horizontally/vertically,
    rotation_deg > 0 = clockwise on screen; b = constant offset (px).
    ``n`` = weighted number of jumps."""
    P = played_notes(O)
    usable = P["head_hit"] | (P["miss_reason"] == "aim")
    d = P[usable & (P["dist_norm"] >= min_dist_norm)].dropna(subset=["start_x", "start_y", "err_dx", "err_dy"])
    w = _w(d).to_numpy(float)
    n = float(w.sum())
    if len(d) < 40 or n < 40:
        return None
    ix = (d["x"] - d["start_x"]).to_numpy()
    iy = (d["y"] - d["start_y"]).to_numpy()
    ex = d["err_dx"].to_numpy()
    ey = d["err_dy"].to_numpy()
    X = np.column_stack([ix, iy, np.ones(len(d))])
    sw = np.sqrt(w)
    cx, *_ = np.linalg.lstsq(X * sw[:, None], ex * sw, rcond=None)
    cy, *_ = np.linalg.lstsq(X * sw[:, None], ey * sw, rcond=None)
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
    var = float(((w * resid_x**2).sum() + (w * resid_y**2).sum()) / 2 / n)
    se_off = math.sqrt(var / n)
    radius = float(d["radius"].median()) if "radius" in d else 36.5
    return {
        "n": int(round(n)),
        "scale_x": float(S[0, 0]),
        "scale_y": float(S[1, 1]),
        "rotation_deg": rot,
        "offset_x": float(cx[2]),
        "offset_y": float(cy[2]),
        "offset_se": se_off,
        "residual_px": math.sqrt(var),
        "radius": radius,
    }


CLICK_BANDS = [
    (0.0, 0.25, "≤ ¼"),
    (0.25, 0.5, "¼–½"),
    (0.5, 0.75, "½–¾"),
    (0.75, 1.0, "¾–1"),
    (1.0, math.inf, "outside"),
]


def click_points(O: pd.DataFrame, frame: str = "screen") -> pd.DataFrame:
    """Where clicks land, in circle radii from the note centre: the click that hit each circle /
    slider head, and the closest click of every aim miss (misses without a click aren't clicks).

    ``frame="screen"``: x right, y down, as on screen — every hit note. ``"movement"``: jumps only,
    rotated so each jump goes right (x = overshoot, y = clockwise side); a constant offset averages
    out in this frame, so it can only be seen on screen. ``w`` = replay weight."""
    P = played_notes(O)
    S = P[P["head_hit"] | (P["miss_reason"] == "aim")]
    if frame == "movement":
        S = S[S["dist_norm"] >= 1]
        x, y = S["along"], S["cross"]
    else:
        x, y = S["err_dx"] / S["radius"], S["err_dy"] / S["radius"]
    out = pd.DataFrame(
        {
            "x": x.to_numpy(float),
            "y": y.to_numpy(float),
            "radius": S["radius"].to_numpy(float),
            "hit": S["head_hit"].to_numpy(bool),
            "w": _w(S).to_numpy(float),
        }
    )
    return out.dropna(subset=["x", "y"]).reset_index(drop=True)


def click_summary(C: pd.DataFrame) -> dict:
    """Average click (osu!px, with a 95% margin), spread, and the share of clicks by distance from the
    centre (``bands``, "outside" = beyond the circle's edge). Weighted by ``w`` if present."""
    n = len(C)
    if not n:
        return {"n": 0}
    w = _w(C)
    px, py = C["x"] * C["radius"], C["y"] * C["radius"]
    d = pd.Series(np.hypot(C["x"], C["y"]), index=C.index)
    sd = (_wstd(px, w), _wstd(py, w)) if n > 1 else (math.nan, math.nan)
    neff = float(w.sum() ** 2 / max(float((w**2).sum()), 1e-12))
    ci = 1.96 * math.hypot(*sd) / math.sqrt(2 * neff) if n > 1 else math.nan
    bands = {label: _rate((d > lo) & (d <= hi) if lo > 0 else (d <= hi), w) for lo, hi, label in CLICK_BANDS}
    return {
        "n": n,
        "mean_px": (_wmean(px, w), _wmean(py, w)),
        "mean_r": (_wmean(C["x"], w), _wmean(C["y"], w)),
        "ci_px": ci,
        "sd_px": sd,
        "median_r": _wquantile(d, w, 0.5),
        "outside": bands["outside"],
        "bands": bands,
        "radius": float(C["radius"].median()),
    }


def aim_split(P: pd.DataFrame, model) -> dict:
    """Aim misses on normal-speed patterns vs speed-aim misses on fast patterns, each against the misses the
    difficulty of those notes predicts (the player's own model): ``{"split": {"aim": {...}, "speed_aim": {...}}}``
    with weighted ``notes``, ``misses`` (of that cause), ``all_misses`` and ``expected`` (all causes)."""
    if P.empty or "miss_cause" not in P:
        return {}
    fast = fast_pattern(P)
    W = _w(P)
    out = {}
    for name, mask in (("aim", ~fast), ("speed_aim", fast)):
        d = P[mask]
        wm = W[mask]
        exp = float(np.nansum(model(d["local_eq"].to_numpy()) * wm.to_numpy())) if len(d) else 0.0
        out[name] = {
            "notes": float(wm.sum()),
            "misses": float(((d["miss_cause"] == name) * wm).sum()),
            "all_misses": float(((~d["head_hit"].astype(bool)) * wm).sum()),
            "expected": exp,
        }
    return {"split": out}


# ------------------------------------------------------------------ jump aim
AIM_TOP = 30  # per play: the 30 fastest jumps (cursor speed needed) set its intensity
AIM_COMBO_POWER = 0.8  # x (your max combo / the map's max combo)^0.8, like osu!'s pp
AIM_REF = 17.5  # 50 = this value at 6 stars (16 → 17.5 after review: aim read a little high) ...
AIM_REF_STEP = 12.0  # ... x2 every 12 stars (the cursor speed of jumps grows slowly with star rating)
AIM_POINTS = 25.0  # points per doubling of the value


def aim_values(P: pd.DataFrame) -> pd.DataFrame:
    """Per passed play: ``intensity`` = average cursor speed of its 30 fastest jumps (distance in circle diameters
    / the time you have to move there, real seconds: distance x speed), ``combo`` = your max combo / the map's,
    ``value`` = intensity x combo^0.8 (like osu!'s pp: a hard map only counts fully when you hold the combo)."""
    cols = ["replay_key", "map", "intensity", "combo", "value", "jumps"]
    if P is None or P.empty or "pattern" not in P or "velocity_real" not in P:
        return pd.DataFrame(columns=cols)
    J = P[P["pattern"].isin(["jump", "spaced"])]
    if "completed" in J:
        J = J[J["completed"].astype(bool)]
    if J.empty:
        return pd.DataFrame(columns=cols)
    diam = 2 * J["radius"].astype(float).clip(lower=1.0) if "radius" in J else 64.0
    J = J.assign(v=J["velocity_real"].astype(float) * 1000.0 / diam, map=_map_key(J).to_numpy())
    rows = []
    for (k, m), d in J.groupby(["replay_key", "map"], sort=False):
        v = d["v"].dropna()
        if len(v) < 10:
            continue
        inten = float(v.nlargest(AIM_TOP).mean())
        c = d["combo_ratio"].iloc[0] if "combo_ratio" in d else 1.0
        c = 1.0 if c is None or not np.isfinite(c) else float(c)
        rows.append(
            {
                "replay_key": k,
                "map": m,
                "intensity": inten,
                "combo": c,
                "value": inten * c**AIM_COMBO_POWER,
                "jumps": int(len(v)),
            }
        )
    return pd.DataFrame(rows, columns=cols)


def aim_ref(level: float | None) -> float:
    lv = 6.0 if level is None or not np.isfinite(level) else float(level)
    return AIM_REF * 2 ** ((lv - 6.0) / AIM_REF_STEP)


def aim_score(P: pd.DataFrame, level: float | None = None, n_total: int | None = None) -> dict:
    """Jump aim: distance x speed x combo (:func:`aim_values`), one value per map (your best pass of it), weighted
    like osu!'s pp (:func:`ranked_mean`); 50 = typical for your level, +25 per doubling."""
    out = {
        "score": None,
        "n": 0,
        "value": math.nan,
        "ref": aim_ref(level),
        "intensity": math.nan,
        "combo": math.nan,
        "maps": 0,
        "best": None,
    }
    V = aim_values(P)
    if V.empty:
        return out
    out["n"] = int(V["jumps"].sum())
    B = V.sort_values("value", ascending=False).drop_duplicates("map")
    N = n_total or _n_replays(P)
    w = rank_weights(N, len(B))
    out["maps"] = int(len(B))
    out["value"] = ranked_mean(B["value"].to_numpy(), N)
    out["intensity"] = float((B["intensity"].to_numpy() * w).sum() / w.sum()) if w.sum() > 0 else math.nan
    out["combo"] = float((B["combo"].to_numpy() * w).sum() / w.sum()) if w.sum() > 0 else math.nan
    out["best"] = {"intensity": float(B["intensity"].iloc[0]), "combo": float(B["combo"].iloc[0])}
    if len(B) >= 3:
        out["score"] = _clip(50 + AIM_POINTS * math.log2(max(out["value"], 1e-6) / out["ref"]))
    return out


# ------------------------------------------------------------------ flow aim
FLOW_TOP = 50  # per play: the 50 fastest spaced-stream notes set its cursor speed
FLOW_AMOUNT = 100.0  # spaced-stream notes for the full amount: ×(notes / 100)^0.25, 0.6–1.5
FLOW_AMOUNT_RANGE = (0.6, 1.5)
FLOW_REF = 11.0  # 50 = this value at 6 stars, ×2 every 12 stars (10 → 11 after review)
FLOW_REF_STEP = 12.0
FLOW_POINTS = 25.0


def flow_values(P: pd.DataFrame) -> pd.DataFrame:
    """Per passed play, flow aim = speed × intensity × combo: ``speed`` = average cursor speed of its 50 fastest
    spaced-stream notes (bursts / streams of notes 0.9+ circle widths apart: distance in circle widths ÷ the real
    time to the next note, so wider spacing and a higher BPM both raise it); ``amount`` = (spaced-stream notes ÷
    100)^0.25 (0.6–1.5: a map full of long flowing streams counts more than one short one); ``combo`` = your max
    combo ÷ the map's, ^0.8 like pp. ``value`` = speed × amount × combo^0.8."""
    cols = ["replay_key", "map", "speed", "amount", "combo", "value", "notes"]
    need = {"spaced_stream", "velocity_real", "run_pos"}
    if P is None or P.empty or not need <= set(P.columns):
        return pd.DataFrame(columns=cols)
    F = P[P["spaced_stream"].astype(bool) & (P["run_pos"] > 0)]
    if "completed" in F:
        F = F[F["completed"].astype(bool)]
    if F.empty:
        return pd.DataFrame(columns=cols)
    diam = 2 * F["radius"].astype(float).clip(lower=1.0) if "radius" in F else 64.0
    F = F.assign(v=F["velocity_real"].astype(float) * 1000.0 / diam, map=_map_key(F).to_numpy())
    rows = []
    for (k, m), d in F.groupby(["replay_key", "map"], sort=False):
        v = d["v"].dropna()
        if len(v) < 20:
            continue
        speed = float(v.nlargest(FLOW_TOP).mean())
        amount = float(np.clip((len(v) / FLOW_AMOUNT) ** 0.25, *FLOW_AMOUNT_RANGE))
        c = d["combo_ratio"].iloc[0] if "combo_ratio" in d else 1.0
        c = 1.0 if c is None or not np.isfinite(c) else float(c)
        rows.append(
            {
                "replay_key": k,
                "map": m,
                "speed": speed,
                "amount": amount,
                "combo": c,
                "value": speed * amount * c**AIM_COMBO_POWER,
                "notes": int(len(v)),
            }
        )
    return pd.DataFrame(rows, columns=cols)


def flow_score(P: pd.DataFrame, level: float | None = None, n_total: int | None = None) -> dict:
    """Flow aim (:func:`flow_values`), one value per map (best pass), weighted like osu!'s pp; 50 = typical for
    your level (10 at 6★, ×2 every 12★), +25 per doubling."""
    lv = 6.0 if level is None or not np.isfinite(level) else float(level)
    out = {
        "score": None,
        "n": 0,
        "value": math.nan,
        "ref": FLOW_REF * 2 ** ((lv - 6.0) / FLOW_REF_STEP),
        "speed": math.nan,
        "combo": math.nan,
        "maps": 0,
    }
    V = flow_values(P)
    if V.empty:
        return out
    B = V.sort_values("value", ascending=False).drop_duplicates("map")
    N = n_total or _n_replays(P)
    w = rank_weights(N, len(B))
    out.update(
        n=int(V["notes"].sum()),
        maps=int(len(B)),
        value=ranked_mean(B["value"].to_numpy(), N),
        speed=float((B["speed"].to_numpy() * w).sum() / w.sum()),
        combo=float((B["combo"].to_numpy() * w).sum() / w.sum()),
    )
    if len(B) >= 3:
        out["score"] = _clip(50 + FLOW_POINTS * math.log2(max(out["value"], 1e-6) / out["ref"]))
    return out
