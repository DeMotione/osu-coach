"""Aggregate many replay analyses into a player profile.

Everything here is computed from replays only:
* the player's level (comfort star rating of the recent replays) and a weight per replay by how far its
  star rating is from that level (``replay_weight``): plays far below or above the level (a 1.5★ warm-up,
  a 9★ map played for fun) hardly count, so they don't distort the numbers;
* overview, miss breakdown (why misses happen, incl. *speed-aim*: aim misses in streams / very fast
  jumps, where the cursor couldn't keep up with the tempo),
* tapping (UR, bias, stream speed profile, alternation, key holds, extra taps, falling behind in streams),
* aim (spacing / direction / angle / quadrant / heat-map, over-/undershoot and an
  affine "tablet area" regression),
* sliders, reading, consistency,
* skill scores: observed vs expected misses where "expected" comes from a
  logistic model of the player's own miss chance against local difficulty
  (osu! strain model, star-equivalent per 400 ms section).

Every statistic is weighted by the replay weight (column ``w`` on the objects and presses).
"""
from __future__ import annotations

import datetime as _dt
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
# Shown when the cursor is on a skill bar (Overview): what the skill measures, how the score is worked out,
# and what raises it. Keep in step with ``_skills`` / ``stamina_score``.
MISS_MODEL_SCORE = ("Score: your misses here vs what your own miss model expects for each note's difficulty; "
                    "hardest plays count most (pp-style). 50 = as expected; each halving of misses = +35.")
SKILL_HELP = {
    "aim": ("Jumps and spaced single notes: notes at least 2 circle widths apart that are not part of a stream "
            "or burst.", MISS_MODEL_SCORE,
            "Practise jump maps slightly above your comfort level, and keep your tablet area / sensitivity fixed "
            "while you do."),
    "flow_aim": ("Spaced streams: bursts and streams (3+ notes in a row) whose notes are about a circle width or "
                 "more apart, so the cursor has to keep moving while you tap.", MISS_MODEL_SCORE,
                 "Spaced-stream maps at a BPM you can tap cleanly, then raise the BPM step by step. Move the arm "
                 "in one smooth motion instead of stopping on every note."),
    "speed": ("Tapping speed: how fast you tap bursts and streams (3+ notes) cleanly: no finger miss (no tap, "
              "too early or late, notelock; cursor misses don't count) and 80%+ of the notes as 300s.",
              "Score: per map the 3rd fastest clean run; maps weighted like osu! pp (fastest 100%, then 1/(replays) "
              "less each); 50 = the stream speed typical for your level, 10% faster ≈ +10.",
              "Stream and burst maps 10–20 BPM above the speed you tap cleanly, in short sets with relaxed "
              "fingers. See the Tapping page for your clean stream speed."),
    "stamina": ("Stamina: for how long you keep a high tempo before your fingers give in (you start "
                "undertapping), not how accurate you stay.",
                "Score: the fastest tempo you kept up for 10 s, 30 s, 1, 2 and 5 min while pressing 90%+ of the "
                "notes (overstreaming is fine); maps weighted like osu! pp, against your level's typical tempo "
                "for that long; 10% faster ≈ +10. Average of the durations.",
                "Play stream-heavy maps that are a little longer than usual and keep tapping to the end, even "
                "when accuracy drops; make the stretches longer first, then faster."),
    "accuracy": ("Hit timing on single notes (not in streams): how many of them you hit as 300s.",
                 "Score: (300 share − 50%) ÷ 49% × 100, so 99% 300s = 100 and 50% = 0 (top players' plays on "
                 "single notes: 95–100%). Needs 60+ single notes.",
                 "Play maps you can full-combo and aim for 300s, not the combo. If your hits lean early or late "
                 "(Tapping page), fix your offset first."),
    "sliders": ("Slider control: how hard the sliders are that you follow to the end without a break: "
                "speed, length, shape, speed changes and how soon the next note comes.",
                "Score: per map your 30 hardest sliders (whose head you hit), average difficulty × share held³; "
                "maps weighted like osu! pp, against your level's typical value, +25 per doubling.",
                "Play maps with long, curved and fast sliders and follow every one to its end; mix slow and fast "
                "sliders. Many short sliders don't raise it."),
    "reading": ("Reading: notes in the dense parts of your maps, where the most notes are on screen at once "
                "(the busiest 20% of notes, at least 4 visible).", MISS_MODEL_SCORE,
                "Maps that are a little denser or have a slightly higher AR than you usually play; HD on "
                "easier maps also trains reading."),
    "consistency": ("Consistency: does one miss make you miss more? The 10 notes after each miss are checked "
                    "(notelock is ignored).",
                    "Score: misses after a miss vs what the difficulty predicts there. A ratio of 2.0 (typical) "
                    "= 50; each halving = +30, each doubling = −30.",
                    "After a miss, reset and play the next note as if the combo were fresh; full-combo runs on "
                    "easier maps build this."),
}
MISS_LABELS = {
    "aim": "aim — tapped in time but outside the circle (jumps and single notes)",
    "speed_aim": "speed-aim — tapped in time, but the cursor couldn't keep up with a stream, burst or very fast "
                 "jump",
    "early": "too early — cursor on the note, tap outside the hit window",
    "late": "too late — cursor on the note, tap after the hit window",
    "no_tap": "no tap — cursor was on the note but no key was pressed",
    "lost": "lost — no tap and the cursor far away (didn't see / read it)",
    "notelock": "notelock — tap ignored because the previous note was still active",
}
TAP_MISSES = ("early", "late", "no_tap", "notelock", "lost")   # misses of the fingers, not of the cursor
FAST_JUMP_MS = 125.0     # jumps this close in time (1/2 at 240 BPM, real time) are "very fast"

# ---- difficulty weighting
LEVEL_BAND = 0.5         # ★: replays within ± this of the player's level count fully
LEVEL_SIGMA = 0.5        # ★: Gaussian fall-off outside the band
RECENT_DAYS = 30         # the level is measured on the replays of the last 30 days (before the newest one) ...
RECENT_MIN = 15          # ... or on the newest 15 if there are fewer
MIN_WEIGHT = 1e-6


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
    model: object = field(default=None, repr=False)   # miss chance by local difficulty (fit_miss_model)
    miss_breakdown_raw: dict = field(default_factory=dict)   # the same, unweighted counts
    fall_behind: dict = field(default_factory=dict)          # stream_fall_behind()


# ------------------------------------------------------------------ helpers
def _played(O: pd.DataFrame) -> pd.DataFrame:
    return O[(O["played"]) & (O["kind"] != "spinner")]


def _w(d: pd.DataFrame) -> pd.Series:
    """Replay weights of the rows (1 where there are none)."""
    if "w" in d:
        return d["w"].astype(float)
    return pd.Series(1.0, index=d.index)


def _rate(miss: pd.Series, w: pd.Series | None = None) -> float:
    if not len(miss):
        return math.nan
    if w is None:
        return float(miss.mean())
    s = float(w.sum())
    return float((miss.astype(float) * w).sum() / s) if s > 0 else math.nan


def _wmean(x: pd.Series, w: pd.Series | None = None) -> float:
    ok = x.notna()
    if not ok.any():
        return math.nan
    if w is None:
        return float(x[ok].mean())
    ww = w[ok]
    s = float(ww.sum())
    return float((x[ok].astype(float) * ww).sum() / s) if s > 0 else math.nan


def _wstd(x: pd.Series, w: pd.Series | None = None) -> float:
    ok = x.notna()
    if ok.sum() < 2:
        return math.nan
    xv = x[ok].astype(float).to_numpy()
    wv = np.ones(len(xv)) if w is None else w[ok].astype(float).to_numpy()
    s = wv.sum()
    if s <= 0:
        return math.nan
    m = (xv * wv).sum() / s
    return float(math.sqrt(max((wv * (xv - m) ** 2).sum() / s, 0.0)))


def _wquantile(x: pd.Series, w: pd.Series | None, q: float) -> float:
    ok = x.notna() & np.isfinite(pd.to_numeric(x, errors="coerce").astype(float))
    if not ok.any():
        return math.nan
    xv = x[ok].astype(float).to_numpy()
    wv = np.ones(len(xv)) if w is None else w[ok].astype(float).to_numpy()
    order = np.argsort(xv)
    xv, wv = xv[order], wv[order]
    cw = np.cumsum(wv)
    if cw[-1] <= 0:
        return math.nan
    i = int(np.searchsorted(cw, q * cw[-1]))
    return float(xv[min(i, len(xv) - 1)])


def _ur(errs: pd.Series, w: pd.Series | None = None) -> float:
    errs = errs.dropna()
    if len(errs) <= 5:
        return math.nan
    if w is None:
        return float(10 * errs.std(ddof=0))
    return 10 * _wstd(errs, w.loc[errs.index])


def _n(d: pd.DataFrame) -> float:
    """Weighted number of rows (= rows when unweighted)."""
    return float(_w(d).sum())


def _clip(v, lo=0.0, hi=100.0):
    return float(min(hi, max(lo, v)))


def _score_from_ratio(expected: float, observed: float) -> float:
    """50 = as expected, each halving of misses vs expectation = +35."""
    expected = max(expected, 1e-6)
    observed = max(observed, 0.5)  # Laplace-ish floor, avoids infinite scores
    return _clip(50 + 35 * math.log2(expected / observed))


# ------------------------------------------------------------------ difficulty weighting
def replay_weight(stars, level: float, band: float = LEVEL_BAND, sigma: float = LEVEL_SIGMA) -> np.ndarray:
    """Weight of a replay by the distance of its star rating (with mods) from the player's level: 1 within
    ± ``band``, then a Gaussian tail (``sigma``): 1★ off ≈ 0.61, 1.5★ ≈ 0.14, 2★ ≈ 0.01, 3★ ≈ 0.00004.
    Unknown star rating or level = 1."""
    s = np.asarray(stars, dtype=float)
    if level is None or not np.isfinite(level):
        return np.ones_like(s)
    d = np.maximum(np.abs(s - level) - band, 0.0)
    w = np.exp(-0.5 * (np.nan_to_num(d) / sigma) ** 2)
    return np.where(np.isfinite(s), np.maximum(w, MIN_WEIGHT), 1.0)


def _utc(v) -> _dt.datetime | None:
    try:
        t = pd.Timestamp(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(t):
        return None
    return (t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")).to_pydatetime()


def detect_level(metas: pd.DataFrame) -> dict:
    """The player's level: comfort star rating (see :func:`comfort_stars`) of the recent replays — the last
    ``RECENT_DAYS`` days before the newest one, or the newest ``RECENT_MIN`` if there are fewer."""
    out = {"level": math.nan, "recent_n": 0, "recent_since": None}
    if metas is None or metas.empty or "stars" not in metas:
        return out
    dates = metas["date"] if "date" in metas else pd.Series([None] * len(metas), index=metas.index)
    m = metas.assign(_t=[_utc(d) for d in dates])
    m = m.sort_values("_t", ascending=False, na_position="last")
    dated = m[m["_t"].notna()]
    if len(dated):
        since = dated["_t"].iloc[0] - _dt.timedelta(days=RECENT_DAYS)
        recent = dated[dated["_t"] >= since]
        if len(recent) < RECENT_MIN:
            recent = m.head(RECENT_MIN)
    else:
        recent = m
    out["level"] = comfort_stars(recent.drop(columns="_t"))
    out["recent_n"] = int(len(recent))
    t = recent["_t"].dropna()
    out["recent_since"] = t.min() if len(t) else None
    return out


def weight_table(level: float, band: float = LEVEL_BAND, sigma: float = LEVEL_SIGMA) -> list[tuple[float, float]]:
    """(★ off the level, weight) pairs for explanations."""
    return [(d, float(replay_weight([level + d], level, band, sigma)[0])) for d in (0.5, 1.0, 1.5, 2.0, 3.0)]


# ------------------------------------------------------------------ miss causes
def fast_pattern(O: pd.DataFrame) -> pd.Series:
    """Bursts and streams (3+ notes at 1/4 or faster, any spacing) and very fast jumps (≤ 125 ms apart)."""
    fast = O["run_len"] >= 3 if "run_len" in O else pd.Series(False, index=O.index)
    if "pattern" in O and "dt_real" in O:
        fast = fast | (O["pattern"].isin(["jump", "spaced"]) & (O["dt_real"] <= FAST_JUMP_MS))
    return fast.fillna(False).astype(bool)


def miss_causes(O: pd.DataFrame) -> pd.Series:
    """The reason of every head miss, with aim misses split by pattern: ``speed_aim`` for aim misses on fast
    patterns (:func:`fast_pattern`) — the tap was in time but the cursor couldn't keep up with the tempo;
    ``aim`` for the rest (jumps at normal speed, single notes). Hits are None."""
    reason = O["miss_reason"] if "miss_reason" in O else pd.Series(None, index=O.index, dtype=object)
    cause = reason.where(~O["head_hit"].astype(bool), None).astype(object)
    cause[(cause == "aim") & fast_pattern(O)] = "speed_aim"
    return cause


# ------------------------------------------------------------------ aim
def quadrant_stats(O: pd.DataFrame) -> pd.DataFrame:
    P = _played(O)
    rows = []
    for q in QUADRANTS:
        d = P[P["quadrant"] == q]
        w = _w(d)
        miss = ~d["head_hit"]
        aim = d["miss_reason"] == "aim"
        aim_rows = d[d["head_hit"] | aim]
        aw = _w(aim_rows)
        rows.append({
            "quadrant": q, "objects": float(w.sum()), "misses": float((miss * w).sum()), "miss_rate": _rate(miss, w),
            "aim_misses": float((aim * w).sum()),
            "aim_miss_rate": _rate(aim, w),
            "mean_dx": _wmean(aim_rows["err_dx"], aw) if len(aim_rows) else math.nan,
            "mean_dy": _wmean(aim_rows["err_dy"], aw) if len(aim_rows) else math.nan,
            "along": _wmean(d["along"], w) if "along" in d and d["along"].notna().any() else math.nan,
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
            "z": float(z), "objects": int(round(n1)), "misses": int(round(m1)),
            "mean_dx": float(row["mean_dx"]), "mean_dy": float(row["mean_dy"]), "along": float(row["along"]),
            "aim_miss_rate": float(row["aim_miss_rate"]),
            "significant": bool(z > 2.0 and n1 >= 80 and m1 >= 8 and rr >= 1.25)}


def grid_stats(O: pd.DataFrame) -> pd.DataFrame:
    P = _played(O)
    P = P.assign(_w=_w(P), _m=(~P["head_hit"]).astype(float) * _w(P))
    g = P.groupby("grid").agg(objects=("_w", "sum"), misses=("_m", "sum"))
    g["miss_rate"] = g["misses"] / g["objects"]
    return g.reindex(range(9)).fillna({"objects": 0, "misses": 0})


def direction_stats(O: pd.DataFrame) -> pd.DataFrame:
    P = _played(O)
    P = P[P["dist_norm"] >= 1.0]
    rows = []
    for d in DIR8:
        s = P[P["dir8"] == d]
        w = _w(s)
        rows.append({"direction": d, "objects": float(w.sum()), "miss_rate": _rate(~s["head_hit"], w),
                     "aim_miss_rate": _rate(s["miss_reason"] == "aim", w),
                     "along": _wmean(s["along"], w) if len(s) else math.nan,
                     "cross": _wmean(s["cross"], w) if len(s) else math.nan})
    return pd.DataFrame(rows).set_index("direction")


def _wgroup(P: pd.DataFrame, by: str, aim_err: bool = False) -> pd.DataFrame:
    """Weighted objects / miss rate / mean over-undershoot (``along``) per group."""
    w = _w(P)
    has = P["along"].notna()
    D = P.assign(_w=w, _m=(~P["head_hit"]).astype(float) * w, _a=P["along"].fillna(0.0) * w,
                 _aw=w.where(has, 0.0))
    g = D.groupby(by, observed=False).agg(objects=("_w", "sum"), misses=("_m", "sum"), _a=("_a", "sum"),
                                          _aw=("_aw", "sum"))
    g["miss_rate"] = (g["misses"] / g["objects"]).where(g["objects"] > 0)
    g["along"] = (g["_a"] / g["_aw"]).where(g["_aw"] > 0)
    g = g.drop(columns=["_a", "_aw", "misses"])
    if aim_err:
        g["aim_err"] = P.groupby(by, observed=False)["aim_err"].median()
    return g


def distance_stats(O: pd.DataFrame) -> pd.DataFrame:
    P = _played(O).dropna(subset=["dist_norm"])
    bins = [0, 0.5, 1, 1.5, 2, 3, 4, 100]
    labels = ["<0.5", "0.5-1", "1-1.5", "1.5-2", "2-3", "3-4", "4+"]
    P = P.assign(dbin=pd.cut(P["dist_norm"], bins=bins, labels=labels, right=False))
    return _wgroup(P, "dbin", aim_err=True)


def angle_stats(O: pd.DataFrame) -> pd.DataFrame:
    P = _played(O).dropna(subset=["angle"])
    P = P[P["dist_norm"] >= 1.0]
    P = P.assign(abin=pd.cut(P["angle"], bins=[0, 60, 120, 181], labels=["sharp (<60°)", "medium", "wide (>120°)"],
                             right=False))
    return _wgroup(P, "abin")


def aim_regression(O: pd.DataFrame, min_dist_norm: float = 1.5) -> dict | None:
    """Fit actual movement = M * intended movement + b on jumps (weighted least squares).

    M is decomposed into rotation R and stretch S (polar decomposition):
    scale_x/scale_y > 1 = moving too far (overaim) horizontally/vertically,
    rotation_deg > 0 = clockwise on screen; b = constant offset (px).
    ``n`` = weighted number of jumps."""
    P = _played(O)
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
    var = float(((w * resid_x ** 2).sum() + (w * resid_y ** 2).sum()) / 2 / n)
    se_off = math.sqrt(var / n)
    radius = float(d["radius"].median()) if "radius" in d else 36.5
    return {"n": int(round(n)), "scale_x": float(S[0, 0]), "scale_y": float(S[1, 1]), "rotation_deg": rot,
            "offset_x": float(cx[2]), "offset_y": float(cy[2]), "offset_se": se_off,
            "residual_px": math.sqrt(var), "radius": radius}


CLICK_BANDS = [(0.0, 0.25, "≤ ¼"), (0.25, 0.5, "¼–½"), (0.5, 0.75, "½–¾"), (0.75, 1.0, "¾–1"),
               (1.0, math.inf, "outside")]


def click_points(O: pd.DataFrame, frame: str = "screen") -> pd.DataFrame:
    """Where clicks land, in circle radii from the note centre: the click that hit each circle /
    slider head, and the closest click of every aim miss (misses without a click aren't clicks).

    ``frame="screen"``: x right, y down, as on screen — every hit note. ``"movement"``: jumps only,
    rotated so each jump goes right (x = overshoot, y = clockwise side); a constant offset averages
    out in this frame, so it can only be seen on screen. ``w`` = replay weight."""
    P = _played(O)
    S = P[P["head_hit"] | (P["miss_reason"] == "aim")]
    if frame == "movement":
        S = S[S["dist_norm"] >= 1]
        x, y = S["along"], S["cross"]
    else:
        x, y = S["err_dx"] / S["radius"], S["err_dy"] / S["radius"]
    out = pd.DataFrame({"x": x.to_numpy(float), "y": y.to_numpy(float), "radius": S["radius"].to_numpy(float),
                        "hit": S["head_hit"].to_numpy(bool), "w": _w(S).to_numpy(float)})
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
    neff = float(w.sum() ** 2 / max(float((w ** 2).sum()), 1e-12))
    ci = 1.96 * math.hypot(*sd) / math.sqrt(2 * neff) if n > 1 else math.nan
    bands = {label: _rate((d > lo) & (d <= hi) if lo > 0 else (d <= hi), w) for lo, hi, label in CLICK_BANDS}
    return {"n": n, "mean_px": (_wmean(px, w), _wmean(py, w)), "mean_r": (_wmean(C["x"], w), _wmean(C["y"], w)),
            "ci_px": ci, "sd_px": sd, "median_r": _wquantile(d, w, 0.5),
            "outside": bands["outside"], "bands": bands, "radius": float(C["radius"].median())}


# ------------------------------------------------------------------ tapping
STREAM_PROFILE_COLUMNS = ["bpm_bin", "objects", "miss_rate", "tap_miss_rate", "speed_aim_rate", "non300_rate", "ur",
                          "ur_best", "ur_plays", "ur_pooled", "mean_err", "ur_trend", "weak"]
UR_MIN_HITS = 10        # hits of one play in a BPM bin needed for that play's UR there
WEAK_UR_FACTOR = 1.15   # a BPM whose UR is this much above the trend (and 15+ UR) is a weak spot
WEAK_UR_MIN = 15.0


def _play_urs(hits: pd.DataFrame, min_hits: int = UR_MIN_HITS) -> pd.DataFrame:
    """UR of every play on its own (``ur``, weight ``w``, hits ``n``). Pooling hits of different plays
    mixes their offsets and conditions and inflates the UR: two plays of 100 UR with averages 10 ms apart
    pool to ~140."""
    hits = hits.dropna(subset=["err_real"])
    key = hits["replay_key"] if "replay_key" in hits else pd.Series("all", index=hits.index)
    rows = []
    for _, g in hits.groupby(key):
        if len(g) < min_hits:
            continue
        w = _w(g)
        rows.append({"ur": _ur(g["err_real"], w), "w": float(w.sum()), "n": len(g)})
    return pd.DataFrame(rows, columns=["ur", "w", "n"])


def ur_trend(prof: pd.DataFrame) -> pd.Series:
    """The UR expected at each stream speed: a weighted straight line through the per-BPM URs, never
    falling with speed (faster streams are not easier), fitted again without the bins far above the first
    line so a weak BPM doesn't pull the line up. Bins far above it are BPMs you are weak at."""
    d = prof.dropna(subset=["ur"])
    if len(d) < 3:
        return pd.Series(math.nan, index=prof.index)
    x, y = d["bpm_bin"].to_numpy(float), d["ur"].to_numpy(float)
    w = np.sqrt(d["objects"].to_numpy(float).clip(min=1))

    def fit(mask):
        slope, icpt = np.polyfit(x[mask], y[mask], 1, w=w[mask])
        if slope < 0:
            slope, icpt = 0.0, float(np.average(y[mask], weights=w[mask]))
        return slope, icpt

    slope, icpt = fit(np.ones(len(x), bool))
    keep = y <= (icpt + slope * x) * WEAK_UR_FACTOR
    if keep.sum() >= 3 and not keep.all():
        slope, icpt = fit(keep)
    return pd.Series(icpt + slope * prof["bpm_bin"].to_numpy(float), index=prof.index)


def stream_speed_profile(O: pd.DataFrame, min_objects: int = 20, min_run: int = 7) -> pd.DataFrame:
    """Miss rate / UR by stream speed (1/4-note BPM, real time). Short bursts are
    left out (min_run): 3-note triplets at 300 BPM say nothing about streaming.

    ``miss_rate`` = all misses; ``tap_miss_rate`` = misses of the fingers (no tap, too early / late,
    notelock, lost) — what stream *speed* is judged on; ``speed_aim_rate`` = aim misses (the cursor fell
    behind, mostly in spaced streams). ``objects`` = weighted note count.

    ``ur`` = the weighted median of the URs of the single plays at that speed (each play with 10+ hits
    there), ``ur_best`` = the lowest of them, ``ur_plays`` = how many plays; ``ur_pooled`` = all hits
    thrown together (the old number, inflated by differences between plays). ``ur_trend`` = the UR the
    other speeds predict (:func:`ur_trend`), ``weak`` = UR clearly above it."""
    P = _played(O)
    S = P[(P["run_len"] >= min_run) & (P["run_pos"] >= 1)].dropna(subset=["stream_bpm"])
    S = S[np.isfinite(S["stream_bpm"].astype(float))]
    if S.empty:
        return pd.DataFrame(columns=STREAM_PROFILE_COLUMNS)
    S = S.assign(bpm_bin=(S["stream_bpm"] // 10 * 10).astype(int))
    reason = S["miss_reason"] if "miss_reason" in S else pd.Series(None, index=S.index, dtype=object)
    rows = []
    for b, d in S.groupby("bpm_bin"):
        w = _w(d)
        if len(d) < min_objects or w.sum() < min_objects:
            continue
        miss = ~d["head_hit"]
        aim = miss & (reason.loc[d.index] == "aim")
        hits = d[d["head_hit"]]
        hw = _w(hits)
        pooled = _ur(hits["err_real"], hw)
        plays = _play_urs(hits)
        if len(plays):
            ur = _wquantile(plays["ur"], plays["w"], 0.5)
            best = float(plays["ur"].min())
        else:
            ur, best = pooled, math.nan
        rows.append({"bpm_bin": int(b), "objects": float(w.sum()), "miss_rate": _rate(miss, w),
                     "tap_miss_rate": _rate(miss & ~aim, w), "speed_aim_rate": _rate(aim, w),
                     "non300_rate": _rate(hits["head_result"] != 300, hw) if len(hits) else math.nan,
                     "ur": ur, "ur_best": best, "ur_plays": len(plays), "ur_pooled": pooled,
                     "mean_err": _wmean(hits["err_real"], hw) if len(hits) else math.nan})
    if not rows:
        return pd.DataFrame(columns=STREAM_PROFILE_COLUMNS)
    prof = pd.DataFrame(rows).sort_values("bpm_bin").reset_index(drop=True)
    prof["ur_trend"] = ur_trend(prof)
    prof["weak"] = ((prof["ur"] > prof["ur_trend"] * WEAK_UR_FACTOR)
                    & (prof["ur"] - prof["ur_trend"] >= WEAK_UR_MIN)).fillna(False).astype(bool)
    return prof[STREAM_PROFILE_COLUMNS]


def stream_limits(prof: pd.DataFrame, base_ur: float) -> dict:
    """Stream speed the player taps cleanly (``comfort_bpm``: ≤ 3% finger misses, UR within 1.6× the
    single-note UR) and where tapping breaks down (``limit_bpm``: ≥ 8% finger misses). Aim misses in
    streams (cursor fell behind) are left out: they are a speed-aim problem, not a tapping-speed one."""
    out = {"comfort_bpm": None, "limit_bpm": None}
    if prof is None or prof.empty:
        return out
    col = "tap_miss_rate" if "tap_miss_rate" in prof else "miss_rate"
    good = prof[(prof["objects"] >= 30) & (prof[col] <= 0.03)
                & ((prof["ur"] <= 1.6 * base_ur) | np.isnan(base_ur))]
    if not good.empty:
        out["comfort_bpm"] = int(good["bpm_bin"].max())
    above = prof[(prof["objects"] >= 30) & (prof[col] >= 0.08)]
    if out["comfort_bpm"] is not None:
        above = above[above["bpm_bin"] > out["comfort_bpm"]]
    if not above.empty:
        out["limit_bpm"] = int(above["bpm_bin"].min())
    return out


def stream_drift(O: pd.DataFrame) -> dict:
    """Timing error vs position inside long runs: +ms per note = falling behind."""
    P = _played(O)
    S = P[(P["run_len"] >= 8) & P["head_hit"]].dropna(subset=["err_real"])
    w = _w(S)
    if len(S) < 60 or w.sum() < 60:
        return {"slope_ms_per_note": math.nan, "late_half_err": math.nan, "early_half_err": math.nan, "n": len(S)}
    slope = np.polyfit(S["run_pos"].to_numpy(dtype=float), S["err_real"].to_numpy(dtype=float), 1,
                       w=np.sqrt(w.to_numpy(float)))[0]
    half = S["run_pos"] >= S["run_len"] / 2
    return {"slope_ms_per_note": float(slope), "late_half_err": _wmean(S.loc[half, "err_real"], w[half]),
            "early_half_err": _wmean(S.loc[~half, "err_real"], w[~half]), "n": int(round(w.sum()))}


FALL_BEHIND_MAX_POS = 128         # notes into a stream looked at
FALL_BEHIND_MIN_RUN = 16          # streams this long or longer
FALL_BEHIND_MIN_SLOPE = 0.1       # ms per note after the onset that counts as "getting less precise"
FALL_BEHIND_MIN_GROWTH = 3.0      # ms, and at least ...
FALL_BEHIND_MIN_GROWTH_SHARE = 0.2   # ... 20% of the precision before the onset
STREAM_LENGTH_GROUPS = [(16, 31, "16–31 notes"), (32, 63, "32–63 notes"), (64, 10**6, "64+ notes")]
STREAM_BIN = 4                    # notes per point on the chart


def stream_fall_behind(O: pd.DataFrame, min_run: int = FALL_BEHIND_MIN_RUN, min_notes: int = 10,
                       reach_bpm: float | None = None) -> dict:
    """Where your precision in long streams starts to fall apart (stamina inside a stream).

    Precision = the average ABSOLUTE timing error (ms) of the hits on the 1st, 2nd, 3rd … note of streams of
    ``min_run``+ notes. (The signed average stays near 0 when early and late hits cancel out, so it can't
    show this.) A tired player's taps scatter more: e.g. 10 ms early in the stream, 50 ms late in it.

    * ``curves``: per stream length group (16–31 / 32–63 / 64+ notes) and per 4 notes (``pos`` = first note
      of the 4): ``abs_err``, ``err`` (signed), ``miss_rate``, ``n`` hits — the chart;
    * ``curve``: per note number (pos, abs_err, err, n) over all of these streams;
    * ``start_note``: where precision starts to get worse — a hinge model abs_err = a + b·max(0, pos − k)
      fitted for every k; None if it doesn't clearly grow. ``base_ms`` = precision before it, ``growth_ms``
      = how much worse by the last note with data, ``start_seconds`` = time to that note at ``bpm``;
    * ``comfort_notes``: stream length you stay precise for (the onset, else the longest stream measured),
      ``practice_notes``: (lo, hi) stream lengths to practise — just past the comfortable length;
    * only streams the player can reach count (``reach_bpm``: clean stream speed + 10, as for stamina):
      far faster streams are imprecise from the first note and say nothing about endurance."""
    out = {"curves": pd.DataFrame(columns=["group", "pos", "abs_err", "err", "miss_rate", "n"]),
           "curve": pd.DataFrame(columns=["pos", "abs_err", "err", "n"]), "start_note": None,
           "start_seconds": None, "bpm": None, "slope_after": math.nan, "growth_ms": math.nan,
           "base_ms": math.nan, "streams": 0, "longest": 0, "comfort_notes": None, "practice_notes": None,
           "reach_bpm": reach_bpm}
    if O is None or O.empty or "run_len" not in O:
        return out
    P = _played(O)
    L = P[(P["run_len"] >= min_run) & (P["run_pos"] < FALL_BEHIND_MAX_POS)]
    if reach_bpm and "stream_bpm" in L:
        L = L[L["stream_bpm"] < reach_bpm + 10]          # 10 BPM bins, as in stamina_score
    S = L[L["head_hit"]].dropna(subset=["err_real"])
    if len(S) < 60:
        return out
    w = _w(S)
    S = S.assign(_w=w, _a=S["err_real"].abs() * w, _e=S["err_real"] * w)
    g = S.groupby("run_pos").agg(sw=("_w", "sum"), sa=("_a", "sum"), se=("_e", "sum"), n=("_w", "size"))
    g = g[(g["n"] >= min_notes) & (g["sw"] > 0)]
    if "replay_key" in S and "run_id" in S:
        out["streams"] = int(len(S.drop_duplicates(subset=["replay_key", "run_id"])))
    out["longest"] = int(L["run_len"].max()) if len(L) else 0
    # chart: per length group, per 4 notes
    rows = []
    Lw = _w(L)
    for lo, hi, label in STREAM_LENGTH_GROUPS:
        sel = (L["run_len"] >= lo) & (L["run_len"] <= hi)
        if not sel.any():
            continue
        G = L[sel]
        Gw = Lw[sel]
        pos_bin = G["run_pos"] // STREAM_BIN * STREAM_BIN
        for b, idx in G.groupby(pos_bin).groups.items():
            d, dw = G.loc[idx], Gw.loc[idx]
            h = d["head_hit"].astype(bool) & d["err_real"].notna()
            if h.sum() < min_notes:
                continue
            rows.append({"group": label, "pos": int(b) + 1, "abs_err": _wmean(d.loc[h, "err_real"].abs(), dw[h]),
                         "err": _wmean(d.loc[h, "err_real"], dw[h]), "miss_rate": _rate(~d["head_hit"], dw),
                         "n": int(h.sum())})
    if rows:
        out["curves"] = pd.DataFrame(rows)
    if len(g) < 6:
        return out
    curve = pd.DataFrame({"pos": g.index.to_numpy() + 1, "abs_err": (g["sa"] / g["sw"]).to_numpy(),
                          "err": (g["se"] / g["sw"]).to_numpy(), "n": g["n"].to_numpy(), "w": g["sw"].to_numpy()})
    out["curve"] = curve[["pos", "abs_err", "err", "n"]]
    bpm = _wquantile(S["stream_bpm"], w, 0.5) if "stream_bpm" in S else math.nan
    out["bpm"] = None if math.isnan(bpm) else float(bpm)
    x, y, cw = curve["pos"].to_numpy(float), curve["abs_err"].to_numpy(float), curve["w"].to_numpy(float)
    sw = np.sqrt(cw)
    best = None
    for k in x[2:-3]:
        h = np.maximum(0.0, x - k)
        X = np.column_stack([np.ones_like(x), h])
        coef, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
        sse = float((cw * (y - X @ coef) ** 2).sum())
        if best is None or sse < best[0]:
            best = (sse, float(k), float(coef[0]), float(coef[1]))
    longest_measured = int(x.max())
    out["comfort_notes"] = longest_measured
    if best is not None:
        _, k, base, slope = best
        out["slope_after"], out["base_ms"] = slope, base
        out["growth_ms"] = slope * (x.max() - k) if slope > 0 else 0.0
        if (slope >= FALL_BEHIND_MIN_SLOPE and out["growth_ms"] >= FALL_BEHIND_MIN_GROWTH
                and out["growth_ms"] >= FALL_BEHIND_MIN_GROWTH_SHARE * max(base, 1.0)):
            out["start_note"] = int(k)
            out["comfort_notes"] = int(k)
            if out["bpm"]:
                out["start_seconds"] = (k - 1) * 15.0 / out["bpm"]   # 1/4 notes: 15000 / BPM ms apart
    c = out["comfort_notes"]
    out["practice_notes"] = (int(c), int(max(c + 8, round(c * 1.5))))
    return out


def tapping_metrics(O: pd.DataFrame, Pr: pd.DataFrame, rates: dict) -> dict:
    P = _played(O)
    hits = P[P["head_hit"]]
    hw = _w(hits)
    single = hits[hits["run_len"] < 3]
    runs = hits[hits["run_len"] >= 3]
    errs = hits["err_real"].dropna()
    ew = hw.loc[errs.index]
    out = {
        "ur": _ur(hits["err_real"], hw), "ur_single": _ur(single["err_real"], _w(single)),
        "ur_streams": _ur(runs["err_real"], _w(runs)),
        "mean_error": _wmean(errs, ew) if len(errs) else math.nan,
        "early_share": _rate(errs < 0, ew) if len(errs) else math.nan,
        "three_hundred_rate_single": _rate(single["head_result"] == 300, _w(single)),
        "timing_miss_share": math.nan,
    }
    misses = P[~P["head_hit"]]
    if len(misses):
        out["timing_miss_share"] = _rate(misses["miss_reason"].isin(["early", "late"]), _w(misses))
    out.update(stream_drift(O))
    if Pr is None or Pr.empty:
        return out
    Pr = Pr.copy()
    pw = _w(Pr)
    Pr["rate"] = Pr["replay_key"].map(rates).fillna(1.0)
    Pr["duration_real"] = Pr["duration"] / Pr["rate"]
    total = len(Pr)
    wtotal = float(pw.sum())
    keys = pw.groupby(Pr["key"]).sum()
    out["key_share"] = {k: float(v / wtotal) for k, v in keys.items()} if wtotal > 0 else {}
    # lazer replays only record left/right ("L"/"R"), not whether a key or a mouse/pen button was used
    legacy_mask = Pr["key"].isin(["K1", "K2", "M1", "M2"])
    legacy = Pr[legacy_mask]
    out["mouse_button_share"] = (_rate(legacy["key"].isin(["M1", "M2"]), pw[legacy_mask])
                                 if len(legacy) >= 200 else math.nan)
    out["key_device_known_share"] = float(pw[legacy_mask].sum() / wtotal) if wtotal > 0 else math.nan
    in_run_mask = Pr["target_run_len"] >= 3
    in_run = Pr[in_run_mask]
    rw = pw[in_run_mask]
    out["alternation_in_streams"] = _rate(in_run["alternated"].astype(bool), rw) if len(in_run) > 30 else math.nan
    half_mask = (Pr["target_pattern"].isin(["jump", "single", "spaced"])) & (Pr["gap_prev"] < 400)
    half = Pr[half_mask]
    out["alternation_singles"] = _rate(half["alternated"].astype(bool), pw[half_mask]) if len(half) > 30 else math.nan
    out["press_ms_median"] = _wquantile(Pr["duration_real"], pw, 0.5)
    out["press_ms_streams"] = _wquantile(in_run["duration"].div(in_run["rate"]), rw, 0.5) if len(in_run) else math.nan
    out["hold_ratio_streams"] = _wquantile(in_run["hold_ratio"], rw, 0.5) if len(in_run) > 30 else math.nan
    # overlapping holds in streams: the other key still down when the next press lands
    out["overlap_in_streams"] = math.nan
    if len(in_run) > 30:
        nxt_gap = Pr["time"].shift(-1) - Pr["time"]
        overlap = (Pr["duration"] > nxt_gap) & in_run_mask
        out["overlap_in_streams"] = _rate(overlap[in_run_mask], rw)
    # very quick re-press of the same key after releasing it (chatter / double taps)
    out["chatter_per_1000"] = float(((Pr["same_key_gap"] <= 20) * pw).sum() / max(wtotal, 1e-9) * 1000)
    # presses that hit nothing while notes were due (overtapping); exclude slider/spinner bodies
    out["extra_presses_per_100"] = _extra_presses(O, Pr)
    out["press_count"] = total
    return out


def _extra_presses(O: pd.DataFrame, Pr: pd.DataFrame) -> float:
    count = 0.0
    n_obj = 0.0
    for key, objs in O.groupby("replay_key"):
        w = float(objs["w"].iloc[0]) if "w" in objs and len(objs) else 1.0
        pr = Pr[(Pr["replay_key"] == key) & (Pr["outcome"] == "none")]
        objs = objs[objs["kind"] != "spinner"]
        n_obj += w * int(objs["played"].sum())
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
            count += w
    return float(count / n_obj * 100) if n_obj > 0 else 0.0


# ------------------------------------------------------------------ expectation model
def fit_miss_model(df: pd.DataFrame, col: str = "local_eq"):
    """Logistic regression P(miss) = s(a + b*eq), weighted by ``w`` if present; returns predict(eq_array)."""
    d = df.dropna(subset=[col])
    y = (~d["head_hit"].astype(bool)).to_numpy(dtype=float)
    x = d[col].to_numpy(dtype=float)
    sw = _w(d).to_numpy(dtype=float)
    wsum = float(sw.sum())
    ymiss = float((y * sw).sum())
    base = ymiss / wsum if wsum > 0 else 0.05
    if len(d) < 50 or wsum < 50 or ymiss < 3 or ymiss > wsum - 3:
        return lambda e: np.full(np.shape(e), base)
    mu = float((x * sw).sum() / wsum)
    sd = float(math.sqrt((sw * (x - mu) ** 2).sum() / wsum)) or 1.0
    z = (x - mu) / sd
    X = np.column_stack([np.ones_like(z), z])
    w = np.array([math.log(max(base, 1e-3) / max(1 - base, 1e-3)), 0.0])
    lam = 1e-3
    for _ in range(50):
        p = _sigmoid(X @ w)
        g = X.T @ (sw * (p - y)) + lam * w
        H = X.T @ (X * (sw * p * (1 - p))[:, None]) + lam * np.eye(2)
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
def build_profile(analyses: list[ReplayAnalysis], level: float | None = None, weighted: bool = True) -> Profile:
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
        o["completed"] = bool(a.meta.get("completed", True))
        o["map_md5"] = a.meta.get("beatmap_md5")
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
    P = _played(O)
    W = _w(P)
    misses = P[~P["head_hit"]]
    mw = _w(misses)
    rw = pd.Series(weights, index=metas.index, dtype=float)

    overview = {
        "replays": len(analyses), "maps": int(metas["beatmap_md5"].nunique()) if len(metas) else 0,
        "weighted_replays": float(rw.sum()),
        "objects": len(P), "head_misses": int(len(misses)), "miss_rate": _rate(~P["head_hit"], W),
        "misses_per_100": 100 * _rate(~P["head_hit"], W),
        "accuracy": _wmean(metas["accuracy"], rw) if len(metas) else math.nan,
        "avg_stars": float(np.average(metas["stars"].fillna(0), weights=metas["n_objects"])) if "stars" in metas and len(metas) else math.nan,
        "max_stars_passed": float(metas.loc[clean_pass(metas), "stars"].max()) if "stars" in metas and clean_pass(metas).any() else math.nan,
        "ur": _ur(P.loc[P["head_hit"], "err_real"], W[P["head_hit"]]),
        "sim_exact_share": float(metas["sim_match"].dropna().astype(float).mean()) if len(metas) else math.nan,
        "sim_agreement": float(pd.to_numeric(metas["sim_agreement"], errors="coerce").mean()) if len(metas) else math.nan,
        "play_minutes": float(metas["length_s"].sum() / 60) if "length_s" in metas else math.nan,
        "first_date": metas["date"].min() if len(metas) else None, "last_date": metas["date"].max() if len(metas) else None,
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
    fall = stream_fall_behind(O, reach_bpm=(tapping["comfort_bpm"] + STAMINA_REACH) if tapping.get("comfort_bpm")
                              else tapping.get("limit_bpm"))

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
        "jump_objects": int(round(jw.sum())), "jump_miss_rate": _rate(~jumps["head_hit"], jw),
        "jump_along": _wmean(jumps["along"], jw) if len(jumps) else math.nan,
        "jump_along_pct": _wquantile(jumps["along"] * jumps["radius"] / jumps["dist"], jw, 0.5) * 100
        if len(jumps) else math.nan,
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
    skills = _skills(P, model, tapping, slider_metrics, reading, consistency, level=used, presses=Pr)
    aim.update(aim_split(P, model))
    strengths, weaknesses = _rank_skills(skills)
    levels = _levels(metas, P, model)
    levels.update(level_stars=used, level_detected=found["level"], level_override=override,
                  level_recent_n=found["recent_n"], level_recent_since=found["recent_since"],
                  level_band=LEVEL_BAND, level_sigma=LEVEL_SIGMA, weighted=bool(weighted))
    return Profile(overview=overview, replays=metas, miss_breakdown=miss_breakdown, slider_breaks=slider_breaks,
                   tapping=tapping, stream_profile=sprof, aim=aim, quadrants=q, worst_quadrant=wq,
                   grid=grid_stats(O), directions=direction_stats(O), distances=distance_stats(O),
                   angles=angle_stats(O), regression=reg, sliders=slider_metrics, reading=reading,
                   consistency=consistency, skills=skills, strengths=strengths, weaknesses=weaknesses,
                   levels=levels, objects=O, presses=Pr, model=model, miss_breakdown_raw=miss_breakdown_raw,
                   fall_behind=fall)


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
        out[name] = {"notes": float(wm.sum()), "misses": float(((d["miss_cause"] == name) * wm).sum()),
                     "all_misses": float(((~d["head_hit"].astype(bool)) * wm).sum()), "expected": exp}
    return {"split": out}


def _reading_metrics(P: pd.DataFrame, misses: pd.DataFrame) -> dict:
    out = {"lost_share": _rate(misses["miss_reason"] == "lost", _w(misses)) if len(misses) else math.nan}
    if len(P):
        W = _w(P)
        thr = max(4, P["density"].quantile(0.8))
        hi = P["density"] >= thr
        out["dense_miss_rate"] = _rate(~P.loc[hi, "head_hit"], W[hi])
        out["sparse_miss_rate"] = _rate(~P.loc[~hi, "head_hit"], W[~hi])
        out["dense_threshold"] = float(thr)
        ar = P["map_ar"]
        hi_ar, lo_ar, mid_ar = ar >= 9.5, ar <= 7, (ar > 7) & (ar < 9.5)
        out["high_ar_miss_rate"] = _rate(~P.loc[hi_ar, "head_hit"], W[hi_ar]) if W[hi_ar].sum() > 50 else math.nan
        out["low_ar_miss_rate"] = _rate(~P.loc[lo_ar, "head_hit"], W[lo_ar]) if W[lo_ar].sum() > 50 else math.nan
        out["mid_ar_miss_rate"] = _rate(~P.loc[mid_ar, "head_hit"], W[mid_ar])
        hd = P["hidden"].astype(bool)
        out["hidden_miss_rate"] = _rate(~P.loc[hd, "head_hit"], W[hd]) if W[hd].sum() > 50 else math.nan
        D = P.assign(ar_bin=(ar * 2).round() / 2, _w=W, _m=(~P["head_hit"]).astype(float) * W)
        g = D.groupby("ar_bin").agg(objects=("_w", "sum"), _m=("_m", "sum"))
        g["miss_rate"] = g["_m"] / g["objects"]
        out["ar_table"] = g.drop(columns="_m").query("objects >= 30")
    return out


def _reading_ratios(P: pd.DataFrame, model) -> dict:
    """Observed / expected misses (the player's own difficulty model) for reading-related
    subsets. Raw miss rates by AR or note density mostly measure that high-AR / dense maps
    are harder; these ratios ask whether you miss *more than their difficulty explains*."""
    out = {}
    if P.empty:
        return out
    W = _w(P)

    def ratio(mask) -> tuple[float, int, float]:
        d = P[mask]
        n = float(W[mask].sum())
        if len(d) < 150 or n < 150:
            return math.nan, int(round(n)), math.nan
        exp = float(np.nansum(model(d["local_eq"].to_numpy()) * W[mask].to_numpy()))
        obs = float(((~d["head_hit"]) * W[mask]).sum())
        return (obs / exp if exp >= 5 else math.nan), int(round(n)), obs

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
                                   "after": recent > 0, "skip": is_nl, "w": _w(d).to_numpy()}))
    if not parts:
        return math.nan
    D = pd.concat(parts, ignore_index=True)
    D = D[~D["skip"]]
    fresh, after = D[~D["after"]], D[D["after"]]
    if len(after) < 20 or len(fresh) < 50 or after["w"].sum() < 20:
        return math.nan
    # expectation from notes with no recent miss, at the same local difficulty
    model = fit_miss_model(fresh)
    exp = float(np.nansum(model(after["local_eq"].to_numpy()) * after["w"].to_numpy()))
    obs = float(((~after["head_hit"]) * after["w"]).sum())
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
    W = _w(P)
    miss = (~P["head_hit"]).astype(float) * W
    out["miss_after_miss_ratio"] = miss_chain_ratio(P)
    end = P["time_frac"] >= 0.8
    out["end_miss_share"] = float(miss[end].sum() / miss.sum()) if miss.sum() > 0 else 0.0
    out["end_object_share"] = _rate(end, W)
    first, second = P["time_frac"] < 0.5, P["time_frac"] >= 0.5
    out["first_half_miss_rate"] = _rate(~P.loc[first, "head_hit"], W[first])
    out["second_half_miss_rate"] = _rate(~P.loc[second, "head_hit"], W[second])
    if len(metas) >= 3:
        out["accuracy_std"] = float(metas["accuracy"].std())
    return out


def _subset_score(P: pd.DataFrame, mask: pd.Series, model, min_n: int = 60) -> dict:
    d = P[mask]
    if len(d) == 0:
        return {"score": None, "n": 0, "observed": 0, "expected": 0}
    W = _w(d)
    n = float(W.sum())
    obs = float(((~d["head_hit"]) * W).sum())
    exp = float(np.nansum(model(d["local_eq"].to_numpy()) * W.to_numpy()))
    score = _score_from_ratio(exp, obs) if (n >= min_n and exp >= 3) else None
    out = {"score": score, "n": int(round(n)), "observed": obs, "expected": exp,
           "miss_rate": obs / n if n > 0 else math.nan, "ratio": obs / exp if exp > 0 else math.nan}
    if score is None and n >= min_n and obs < FEW_MISSES and exp < FEW_MISSES:
        # enough notes, but you (almost) never miss: the score compares misses, so there's nothing to compare
        out["too_few_misses"] = True
    return out


FEW_MISSES = 3            # fewer misses than this (and expected) can't be compared: "too few misses to tell"
FEW_MISSES_NOTES = 500    # ... for consistency, on at least this many notes
ACCURACY_ZERO = 0.50      # accuracy score: 0 at 50% 300s on single notes ...
ACCURACY_TOP = 0.99       # ... 100 at 99% (top players' reference plays: 95–100%, median 98%)


def accuracy_score(r300: float) -> float:
    return _clip((r300 - ACCURACY_ZERO) / (ACCURACY_TOP - ACCURACY_ZERO) * 100)


STAMINA_RUN = 16          # notes: a "long" stream
STAMINA_REACH = 10        # BPM above the clean stream speed that still counts as reachable (precision chart)
STAMINA_MAP_RUN = 8       # streams / bursts this long count towards a map's tapping load
STAMINA_KEPT = 0.9        # share of a stream's notes you must have pressed for: "your fingers kept going"
STAMINA_KEPT_ZERO = 0.6   # ... below this share a stream adds nothing; in between it counts partly
STAMINA_BPM_POWER = 3.0   # a note at 240 BPM loads (240/200)^3 = 1.73x a note at 200 BPM
STAMINA_STEADY_MIN = 0.3      # a stream that falls apart still counts 30% (you kept pressing)
STAMINA_OVERSTREAM = 0.95     # taps ≥ 5% faster than the notes = overstreaming: fine, never penalised
STAMINA_SLOW_FREE = 0.03      # steadiness of a long stream (info): the 2nd half may be 3% slower for free ...
STAMINA_SLOW_COST = 2.5       # ... then each 1% slower costs 2.5%
STAMINA_JITTER_FREE = 0.05    # the 2nd half's rhythm may get this much less even (spread / median) for free
STAMINA_JITTER_COST = 1.0
# stamina = the tempo you keep up for a given time (tempo-duration curve):
STAMINA_WINDOWS = (10, 30, 60, 120, 300)      # seconds
# 50 = this share of the stream speed typical for your level (stamina_ref_bpm), kept up for that long
# (set for the pp-style weighted average of all your maps, not your best few: a 6★ player's history and the 38
# reference plays of ~10★ players give about 0.52 / 0.45 / 0.40 / 0.37 and 0.71 / 0.61 / 0.52 / 0.42 at 10 s … 2 min)
STAMINA_WINDOW_SHARE = {10: 0.55, 30: 0.47, 60: 0.41, 120: 0.38, 300: 0.33}
STAMINA_MIN_MAPS = 2          # a duration counts once 2+ maps were played that long
STAMINA_POINTS = 75.0         # points per doubling of the tempo (≈ 10 points for 10% faster)
PRESSED_REASONS = ("early", "late", "aim", "notelock")   # misses where a key was pressed


def stamina_ref_bpm(level: float | None) -> float:
    """Stream speed typical for a level (★): ~165 BPM at 3★, ~210 at 6★, ~255 at 9★."""
    if level is None or not np.isfinite(level):
        return 200.0
    return float(min(300.0, max(120.0, 120.0 + 15.0 * level)))


def _press_times(presses: pd.DataFrame | None, rates: dict) -> dict:
    """Real-time (ms, rate applied) press times per replay, sorted."""
    if presses is None or presses.empty or "time" not in presses:
        return {}
    out = {}
    for k, d in presses.groupby("replay_key", sort=False):
        out[k] = np.sort(d["time"].to_numpy(float)) / float(rates.get(k, 1.0) or 1.0)
    return out


def stream_rhythm(t: np.ndarray, start: float, end: float, bpm: float) -> dict | None:
    """How steady the taps of one stream were, from the key presses between its first and last note
    (real ms). Gaps are measured over two taps (left + right), so an uneven but regular alternation
    (e.g. a slightly faster left finger) is not "unsteady". Relative to the stream's note spacing:
    ``r1`` / ``r2`` = median tap gap in the 1st / 2nd half (1.0 = exactly with the notes, < 1 = faster:
    overstreaming), ``slow`` = how much slower the 2nd half got (speeding up / overstreaming = 0),
    ``jitter`` = how much less even the 2nd half got. ``steady`` (0.3–1) = the factor its load keeps."""
    gap = 15000.0 / bpm
    tt = t[(t >= start - 0.5 * gap) & (t <= end + 0.5 * gap)]
    if len(tt) < 12:
        return None
    g = (tt[2:] - tt[:-2]) / (2 * gap)
    h = len(g) // 2
    a, b = g[:h], g[h:]
    if len(a) < 4 or len(b) < 4:
        return None

    def spread(x):
        m = float(np.median(x))
        return float(1.4826 * np.median(np.abs(x - m)) / max(m, 1e-6))
    r1, r2 = float(np.median(a)), float(np.median(b))
    slow = max(0.0, r2 / max(r1, 1e-6) - 1.0)
    if r2 <= STAMINA_OVERSTREAM:      # still tapping faster than the notes at the end: overstreaming, fine
        slow = 0.0
    jitter = max(0.0, spread(b) - spread(a))
    steady = 1.0 - STAMINA_SLOW_COST * max(0.0, slow - STAMINA_SLOW_FREE) \
        - STAMINA_JITTER_COST * max(0.0, jitter - STAMINA_JITTER_FREE)
    return {"r1": r1, "r2": r2, "slow": slow, "jitter": jitter, "presses": int(len(tt)),
            "steady": float(min(1.0, max(STAMINA_STEADY_MIN, steady)))}


def stream_loads(P: pd.DataFrame, min_run: int = STAMINA_MAP_RUN, presses: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per stream / burst of ``min_run``+ notes in each play:

    * ``notes``, ``bpm``, ``start`` / ``end`` (real seconds into the map), ``completed`` (map finished);
    * ``kept``: share of its notes you pressed a key for — 100s, 50s and misses where you tapped (also too
      early: overstreaming) count; only no-tap / lost / never reached don't;
    * ``steady`` (0.3–1, from the key presses of streams of 16+ notes, 1 when unknown): did your taps slow
      down or get uneven in the second half? Overstreaming (tapping faster than the notes) is never a loss;
    * ``quality`` = kept part × steady: kept ≥ 90% counts fully, ≤ 60% not at all, linear in between;
    * ``load`` = notes × (BPM / 200)^3 × quality: equivalent notes at 200 BPM, so faster streams weigh much
      more; ``raw_load`` without the quality factor."""
    cols = ["replay_key", "run_id", "notes", "bpm", "start", "end", "kept", "steady", "slow", "overstream",
            "quality", "raw_load", "load", "completed"]
    if P is None or P.empty or "run_id" not in P:
        return pd.DataFrame(columns=cols)
    R = P[(P["run_id"] >= 0) & (P["run_len"] >= min_run)].dropna(subset=["stream_bpm"])
    if R.empty:
        return pd.DataFrame(columns=cols)
    reason = R["miss_reason"] if "miss_reason" in R else pd.Series(None, index=R.index, dtype=object)
    pressed = R["head_hit"].astype(bool) | reason.isin(PRESSED_REASONS)
    key = R["replay_key"] if "replay_key" in R else pd.Series("all", index=R.index)
    done = R["completed"] if "completed" in R else pd.Series(True, index=R.index)
    rate = R["rate"].astype(float).fillna(1.0) if "rate" in R else pd.Series(1.0, index=R.index)
    t = R["time"].astype(float) / rate if "time" in R else pd.Series(np.nan, index=R.index)
    D = pd.DataFrame({"replay_key": key, "run_id": R["run_id"], "pressed": pressed, "notes": R["run_len"],
                      "bpm": R["stream_bpm"].astype(float), "completed": done.astype(bool), "t": t,
                      "rate": rate})
    g = D.groupby(["replay_key", "run_id"], sort=False).agg(
        notes=("notes", "first"), bpm=("bpm", "first"), pressed=("pressed", "sum"), completed=("completed", "first"),
        t0=("t", "min"), t1=("t", "max"), rate=("rate", "first"))
    g = g.reset_index()
    g["kept"] = g["pressed"] / g["notes"].clip(lower=1)   # notes never reached (failed) count as not pressed
    g["start"], g["end"] = g["t0"] / 1000.0, g["t1"] / 1000.0
    times = _press_times(presses, dict(zip(g["replay_key"], g["rate"])))
    steady, slow, over = [], [], []
    for k, n, b, t0, t1 in zip(g["replay_key"], g["notes"], g["bpm"], g["t0"], g["t1"]):
        rh = stream_rhythm(times[k], t0, t1, b) if (n >= STAMINA_RUN and k in times and np.isfinite(t0)) else None
        steady.append(rh["steady"] if rh else 1.0)
        slow.append(rh["slow"] if rh else math.nan)
        over.append(bool(rh and rh["r1"] <= STAMINA_OVERSTREAM))
    g["steady"], g["slow"], g["overstream"] = steady, slow, over
    kept_part = ((g["kept"] - STAMINA_KEPT_ZERO) / (STAMINA_KEPT - STAMINA_KEPT_ZERO)).clip(0, 1)
    g["quality"] = kept_part * g["steady"]
    g["raw_load"] = g["notes"] * (g["bpm"] / 200.0) ** STAMINA_BPM_POWER
    g["load"] = g["raw_load"] * g["quality"]
    return g[cols]


def _map_key(P: pd.DataFrame) -> pd.Series:
    """Beatmap (and rate) of each row, so repeated plays of one map count once; the replay when unknown."""
    key = P["replay_key"].astype(str) if "replay_key" in P else pd.Series("all", index=P.index)
    if "map_md5" in P:
        rate = P["rate"].astype(float).fillna(1.0).round(3).astype(str) if "rate" in P else ""
        return P["map_md5"].fillna(key).astype(str) + "@" + rate
    return key


def tempo_curve(P: pd.DataFrame, windows=STAMINA_WINDOWS) -> pd.DataFrame:
    """Stamina curve of every play: for each duration W (seconds), the fastest tempo you kept up for W seconds.

    Every note you tap (circles and slider heads, not spinners) counts if you pressed a key for it — 300s, 100s,
    50s and misses where you tapped (also too early: overstreaming); only notes you didn't press for (no tap,
    lost, not reached) don't. In every W-second stretch of the play: tempo = pressed notes per second as 1/4-note
    BPM (15 × notes per second, so a 220 BPM stream = 220), × the kept share (pressed 90%+ of the notes there =
    1, 60% or less = 0, linear between): when your fingers start to give in (undertapping), the tempo stops
    counting. ``bpm`` = the best stretch of the play. Only stretches inside what you played count (failed plays
    up to where they ended), and a play shorter than W has no value for W."""
    cols = ["replay_key", "map", "window", "bpm", "minutes"]
    if P is None or P.empty or "time" not in P:
        return pd.DataFrame(columns=cols)
    D = P[P["kind"] != "spinner"] if "kind" in P else P
    if D.empty:
        return pd.DataFrame(columns=cols)
    reason = D["miss_reason"] if "miss_reason" in D else pd.Series(None, index=D.index, dtype=object)
    pressed = (D["head_hit"].astype(bool) | reason.isin(PRESSED_REASONS)).to_numpy()
    rate = D["rate"].astype(float).fillna(1.0).to_numpy() if "rate" in D else np.ones(len(D))
    t_all = D["time"].astype(float).to_numpy() / rate / 1000.0
    keys = D["replay_key"].astype(str).to_numpy() if "replay_key" in D else np.full(len(D), "all")
    maps = _map_key(D).to_numpy()
    rows = []
    for k in pd.unique(keys):
        m = keys == k
        order = np.argsort(t_all[m])
        t, pr = t_all[m][order], pressed[m][order]
        if len(t) < 2:
            continue
        span = t[-1] - t[0]
        cp = np.concatenate([[0], np.cumsum(pr)])
        idx = np.arange(len(t))
        for W in windows:
            if span < W * 0.98:
                continue
            j = np.searchsorted(t, t + W, side="left")
            n = j - idx
            kept = cp[j] - cp[idx]
            share = np.where(n > 0, kept / np.maximum(n, 1), 0.0)
            q = np.clip((share - STAMINA_KEPT_ZERO) / (STAMINA_KEPT - STAMINA_KEPT_ZERO), 0, 1)
            bpm = np.where(t + W <= t[-1] + 0.02 * W, kept / W * 15.0 * q, 0.0)
            rows.append({"replay_key": k, "map": maps[m][0], "window": W, "bpm": float(bpm.max()),
                         "minutes": span / 60.0})
    return pd.DataFrame(rows, columns=cols)


def stamina_score(P: pd.DataFrame, tapping: dict | None = None, level: float | None = None,
                  presses: pd.DataFrame | None = None, n_total: int | None = None) -> dict:
    """Stamina: for how long you keep a high tempo without your fingers giving in — not how accurate you stay.

    osu!standard has no stamina skill of its own: the star rating's speed strain decays to 30% per second
    (osu!lazer ``Speed.cs``), so it only "remembers" the last second or two. This score uses
    :func:`tempo_curve`: the fastest tempo you kept up (still pressing 90%+ of the notes) for 10 s, 30 s, 1 min,
    2 min and 5 min. Overstreaming — tapping faster than the notes — never counts against you.

    * each duration: one value per map (your best play of it), ranked fastest first and weighted like osu!'s pp
      (:func:`ranked_mean`: 100%, then 1/N less per place, N = replays analysed); it counts once 2+ maps were
      played that long;
    * 50 = the tempo typical for your level for that long (``stamina_ref_bpm`` × ``STAMINA_WINDOW_SHARE``: the
      longer, the more pauses and slower parts any map has); 10% faster ≈ +10 points, twice as fast = +75;
    * the score = the average over the durations, so holding a tempo for minutes counts as much as a short
      burst of speed. Low-tempo marathons stay low (they don't show a high tempo), and death streams you can't
      keep up score low for the long durations.

    The steadiness numbers (did your taps slow down or get uneven in the second half of long streams) are shown
    for information. Difficulty weights are not used: the score asks what you *can* sustain."""
    ref_bpm = stamina_ref_bpm(level)
    out = {"score": None, "n": 0, "ref_bpm": ref_bpm, "curve": {}, "parts": {}, "maps": {}, "best": {},
           "ref_curve": {W: ref_bpm * STAMINA_WINDOW_SHARE[W] for W in STAMINA_WINDOWS},
           "streams_long": 0, "streams_kept": 0, "streams_slowed": 0, "streams_overstreamed": 0,
           "steadiness": math.nan, "best_stream": None, "longest_minutes": math.nan}
    C = tempo_curve(P)
    if len(C):
        out["longest_minutes"] = float(C["minutes"].max())
        out["n"] = int(C["map"].nunique())
    for W in STAMINA_WINDOWS:
        c = C[C["window"] == W]
        if c.empty:
            continue
        per_map = c.groupby("map")["bpm"].max().sort_values(ascending=False)
        out["maps"][W] = int(len(per_map))
        if len(per_map) < STAMINA_MIN_MAPS:
            continue
        v = ranked_mean(per_map.to_numpy(), n_total or _n_replays(P))
        out["curve"][W] = v
        out["best"][W] = float(per_map.iloc[0])
        out["parts"][W] = _clip(50 + STAMINA_POINTS * math.log2(max(v, 1e-6) / out["ref_curve"][W]))
    if out["parts"] and out["n"] >= 3:
        out["score"] = float(np.mean(list(out["parts"].values())))
    # information: long streams and how steady your taps stayed in them
    L = stream_loads(P, presses=presses)
    long_all = L[L["notes"] >= STAMINA_RUN] if len(L) else L
    if len(long_all):
        measured = long_all[long_all["slow"].notna()]
        out.update(streams_long=int(len(long_all)), streams_kept=int((long_all["kept"] >= STAMINA_KEPT).sum()),
                   streams_slowed=int((measured["steady"] < 0.95).sum()),
                   streams_overstreamed=int(measured["overstream"].sum()),
                   steadiness=float(np.average(measured["steady"], weights=measured["raw_load"]))
                   if len(measured) else math.nan)
        kept = long_all[long_all["kept"] >= STAMINA_KEPT]
        if len(kept):
            b = kept.sort_values(["raw_load"], ascending=False).iloc[0]
            out["best_stream"] = {"notes": int(b["notes"]), "bpm": float(b["bpm"]), "steady": float(b["steady"])}
    bits = [f"{_dur(W)}: {v:.0f} BPM" for W, v in out["curve"].items()]
    if out["best_stream"]:
        bs = out["best_stream"]
        bits.append(f"hardest stream: {bs['notes']} notes at {bs['bpm']:.0f} BPM")
    if not math.isnan(out["steadiness"]):
        bits.append(f"steadiness {out['steadiness']:.0%}")
    out["detail"] = "; ".join(bits)
    return out


def _dur(W: float) -> str:
    return f"{W:.0f} s" if W < 60 else f"{W / 60:.0f} min"


# ------------------------------------------------------------------ sliders
SLIDER_FOLLOW_SLACK = 1.0   # circle diameters of slider path the follow circle covers without moving
SLIDER_TOP = 30             # per play: the hardest 30 sliders whose head you hit
SLIDER_MIN = 10             # ... a play needs 10+ such sliders
SLIDER_MIN_MAPS = 3
SLIDER_HOLD_POWER = 3.0     # breaking a few of your hardest sliders costs a lot: value × held share³
SLIDER_REF = 40.0           # 50 = this value at 6★ ...
SLIDER_REF_STEP = 3.0       # ... ×2 every 3★ (slider difficulty grows much slower with star rating than aim)
SLIDER_POINTS = 25.0        # points per doubling of the value


def slider_difficulty(S: pd.DataFrame) -> pd.Series:
    """Difficulty of following each slider (0 = the follow circle covers it without moving):

    speed (circle diameters per second the ball moves, real time) × length (log2 of 1 + the path beyond what
    the follow circle covers, in diameters; repeats add log2(repeats)) × shape (1 + half a point per half
    circle of turning, up to 2 full turns, + 0.3 per sharp corner and + 0.2 per left↔right bend, up to 4 each)
    × speed change (1 + |ln(speed / previous slider's speed)|, up to ×2: a slow slider right after a fast one or
    the other way round) × rush (up to ×1.5 when the next note comes less than 250 ms after the slider end)."""
    diam = 2 * S["radius"].astype(float).clip(lower=1.0)
    speed = S["slider_vel_real"].astype(float).fillna(0) * 1000.0 / diam
    eff = (S["slider_len"].astype(float).fillna(0) / diam - SLIDER_FOLLOW_SLACK).clip(lower=0)
    spans = S["slider_spans"].astype(float).fillna(1).clip(lower=1)
    length = np.log2(1 + eff * (1 + np.log2(spans)))
    col = lambda c: S[c].astype(float).fillna(0) if c in S else pd.Series(0.0, index=S.index)  # noqa: E731
    shape = 1 + 0.5 * (col("slider_turn") / math.pi).clip(upper=4) \
        + 0.3 * col("slider_corners").clip(upper=4) + 0.2 * col("slider_bends").clip(upper=4)
    change = 1 + col("slider_vel_change").clip(upper=1.0)
    gap = S["slider_next_gap"].astype(float).fillna(1000.0) if "slider_next_gap" in S else 1000.0
    rush = 1 + 0.5 * ((250.0 - gap) / 250.0).clip(0, 1)
    return speed * length * shape * change * rush


def slider_ref(level: float | None) -> float:
    lv = 6.0 if level is None or not np.isfinite(level) else float(level)
    return SLIDER_REF * 2 ** ((lv - 6.0) / SLIDER_REF_STEP)


def slider_score(P: pd.DataFrame, level: float | None = None, n_total: int | None = None) -> dict:
    """Slider control: how hard the sliders are that you follow to the end — not how many easy ones.

    Every slider whose head you hit gets a difficulty (:func:`slider_difficulty`: speed, length, shape, speed
    changes, rush). Per play, the hardest 30 count: value = their average difficulty × (share you held without
    a break)³, so a play full of short, slow sliders stays low however clean, and breaking 1 of the 30 hardest
    costs about 25%. One value per map (your best play of it), weighted like osu!'s pp (:func:`ranked_mean`); the
    score = 50 + 25 × log2(that ÷ the value typical for your level), so twice the typical value = 75."""
    out = {"score": None, "n": 0, "plays": 0, "value": math.nan, "ref": slider_ref(level), "break_rate": math.nan,
           "top_held": math.nan, "best": None}
    if P is None or P.empty or "kind" not in P:
        return out
    S = P[(P["kind"] == "slider") & P["head_hit"].astype(bool)]
    if "slider_vel_real" not in S or S.empty:
        return out
    S = S.assign(diff=slider_difficulty(S).to_numpy(), held=~S["broke"].fillna(False).astype(bool).to_numpy(),
                 map=_map_key(S).to_numpy())
    out["n"] = int(len(S))
    out["break_rate"] = float(1 - S["held"].mean())
    rows = []
    for (k, m), d in S.groupby(["replay_key", "map"], sort=False):
        if len(d) < SLIDER_MIN:
            continue
        top = d.nlargest(SLIDER_TOP, "diff")
        hold = float(top["held"].mean())
        rows.append({"map": m, "value": float(top["diff"].mean()) * hold ** SLIDER_HOLD_POWER, "hold": hold,
                     "diff": float(top["diff"].mean())})
    if not rows:
        return out
    R = pd.DataFrame(rows).sort_values("value", ascending=False).drop_duplicates("map")
    N = n_total or _n_replays(P)
    w = rank_weights(N, len(R))
    out["plays"] = int(len(R))
    out["value"] = ranked_mean(R["value"].to_numpy(), N)
    out["top_held"] = float((R["hold"].to_numpy() * w).sum() / w.sum()) if w.sum() > 0 else math.nan
    out["best"] = float(R["value"].iloc[0])
    if len(R) >= SLIDER_MIN_MAPS:
        out["score"] = _clip(50 + SLIDER_POINTS * math.log2(max(out["value"], 1e-6) / out["ref"]))
    return out


# ------------------------------------------------------------------ pp-style weighting of the skills
def rank_weights(n_total: int, count: int) -> np.ndarray:
    """Weights of ``count`` plays sorted hardest / best first, like osu!'s pp list but linear: the first counts
    100%, each next one 1/``n_total`` less (100 replays analysed: 100%, 99%, 98%, ...; 50 replays: 2% steps)."""
    n_total = max(int(n_total), 1)
    return np.clip(1.0 - np.arange(count) / n_total, 0.0, 1.0)


def ranked_mean(values, n_total: int) -> float:
    """Weighted average of per-play values, highest first, with :func:`rank_weights`."""
    v = np.sort(np.asarray([x for x in values if x is not None and np.isfinite(x)], dtype=float))[::-1]
    if not len(v):
        return math.nan
    w = rank_weights(n_total, len(v))
    return float((v * w).sum() / w.sum()) if w.sum() > 0 else math.nan


def _n_replays(P: pd.DataFrame) -> int:
    return int(P["replay_key"].nunique()) if "replay_key" in P and len(P) else 1


def difficulty_weights(P: pd.DataFrame, mask: pd.Series | None, col: str = "local_eq",
                       n_total: int | None = None) -> pd.Series:
    """Per-row weights for one skill: its plays ranked by how hard that skill's notes were in them (the 80th
    percentile of ``col`` on the notes in ``mask``; plays without such notes by star rating), hardest = 100%,
    then 1/n less per place (:func:`rank_weights`)."""
    if P.empty:
        return pd.Series(dtype=float)
    key = P["replay_key"] if "replay_key" in P else pd.Series("all", index=P.index)
    src = P[col] if col in P else P.get("local_eq", pd.Series(np.nan, index=P.index))
    d = src.where(mask, np.nan) if mask is not None else src
    hard = d.groupby(key).quantile(0.8)
    if "stars" in P:
        hard = hard.fillna(P["stars"].groupby(key).first())
    hard = hard.fillna(0.0).sort_values(ascending=False)
    w = dict(zip(hard.index, rank_weights(n_total or len(hard), len(hard))))
    return key.map(w).astype(float).fillna(0.0)


def _weighted(P: pd.DataFrame, weights: pd.Series) -> pd.DataFrame:
    Q = P.copy()
    Q["w"] = weights
    return Q


# ------------------------------------------------------------------ tapping speed
SPEED_FINGER = ("no_tap", "early", "late", "notelock")   # finger misses (aim / lost-track misses don't count)
SPEED_TIMING = 0.8        # a clean run: no finger miss and 80%+ of its hit notes as 300s (mashing gives 100s)
SPEED_RUNS = 3            # a play's speed: the 3rd fastest clean burst / stream (one lucky burst doesn't decide)
SPEED_POINTS = 75.0       # points per doubling of the BPM (10% faster ≈ +10), like stamina


def speed_values(P: pd.DataFrame) -> pd.DataFrame:
    """Per play: ``bpm`` = the speed you tap bursts and streams (3+ notes) cleanly — the 3rd fastest run with no
    finger miss (no tap, too early / late, notelock; cursor misses don't count) and 80%+ of its hit notes as 300s.
    Also ``runs`` (all) and ``clean`` (clean runs)."""
    cols = ["replay_key", "map", "bpm", "runs", "clean"]
    if P is None or P.empty or "run_id" not in P:
        return pd.DataFrame(columns=cols)
    R = P[(P["run_id"] >= 0) & (P["run_len"] >= 3)].dropna(subset=["stream_bpm"])
    if R.empty:
        return pd.DataFrame(columns=cols)
    reason = R["miss_reason"] if "miss_reason" in R else pd.Series(None, index=R.index, dtype=object)
    finger = (~R["head_hit"].astype(bool)) & reason.isin(SPEED_FINGER)
    great = (R["head_result"] == 300) if "head_result" in R else R["head_hit"].astype(bool)
    D = pd.DataFrame({"replay_key": R["replay_key"] if "replay_key" in R else "all", "map": _map_key(R),
                      "run_id": R["run_id"], "bpm": R["stream_bpm"].astype(float), "finger": finger,
                      "hit": R["head_hit"].astype(bool), "great": great & R["head_hit"].astype(bool)})
    g = D.groupby(["replay_key", "map", "run_id"], sort=False).agg(bpm=("bpm", "first"), finger=("finger", "sum"),
                                                                    hit=("hit", "sum"), great=("great", "sum"))
    g["clean"] = (g["finger"] == 0) & (g["great"] >= SPEED_TIMING * g["hit"].clip(lower=1))
    rows = []
    for (k, m), d in g.groupby(level=[0, 1], sort=False):
        c = d.loc[d["clean"], "bpm"].sort_values(ascending=False)
        rows.append({"replay_key": k, "map": m, "bpm": float(c.iloc[SPEED_RUNS - 1]) if len(c) >= SPEED_RUNS
                     else math.nan, "runs": int(len(d)), "clean": int(len(c))})
    return pd.DataFrame(rows, columns=cols)


def speed_score(P: pd.DataFrame, level: float | None = None, n_total: int | None = None) -> dict:
    """Tapping speed: how fast you tap bursts and streams cleanly (:func:`speed_values`), one value per map (your
    best play of it), ranked fastest first and weighted like osu!'s pp (:func:`ranked_mean`). 50 = the stream
    speed typical for your level (``stamina_ref_bpm``), 10% faster ≈ +10."""
    ref = stamina_ref_bpm(level)
    out = {"score": None, "n": 0, "bpm": math.nan, "best_bpm": math.nan, "ref_bpm": ref, "maps": 0,
           "clean_share": math.nan}
    V = speed_values(P)
    if V.empty:
        return out
    out["n"] = int(V["runs"].sum())
    out["clean_share"] = float(V["clean"].sum() / max(V["runs"].sum(), 1))
    per_map = V.dropna(subset=["bpm"]).groupby("map")["bpm"].max()
    out["maps"] = int(len(per_map))
    if len(per_map) >= 3:
        out["bpm"] = ranked_mean(per_map.to_numpy(), n_total or _n_replays(P))
        out["best_bpm"] = float(per_map.max())
        out["score"] = _clip(50 + SPEED_POINTS * math.log2(out["bpm"] / ref))
    return out


def _skills(P, model, tapping, sliders, reading, consistency, level: float | None = None,
            presses: pd.DataFrame | None = None) -> dict:
    s = {}
    N = _n_replays(P)
    # every skill: its plays ranked hardest first, 100% / 99% / 98% ... (1/N steps), like osu!'s pp list
    for key, mask, col in (("aim", P["pattern"].isin(["jump", "spaced"]), "aim_eq"),
                           ("flow_aim", P["spaced_stream"].astype(bool), "aim_eq")):
        s[key] = _subset_score(_weighted(P, difficulty_weights(P, mask, col, N)), mask, model)
    s["speed"] = speed_score(P, level, N)
    s["stamina"] = stamina_score(P, tapping, level, presses=presses, n_total=N)
    single = P["run_len"] < 3
    Wa = difficulty_weights(P, None, "stars", N)
    sd = P[single & P["head_hit"].astype(bool)]
    wa = Wa[sd.index]
    r300 = float((wa * (sd["head_result"] == 300)).sum() / wa.sum()) if len(sd) and wa.sum() > 0 else math.nan
    n_single = int(single.sum())
    s["accuracy"] = {"score": accuracy_score(r300) if not math.isnan(r300) and n_single >= 60 else None,
                     "n": n_single, "three_hundred_rate": r300, "ur": tapping.get("ur_single")}
    s["sliders"] = slider_score(P, level, n_total=N)
    if "dense_threshold" in reading:
        mask = P["density"] >= reading["dense_threshold"]
        s["reading"] = _subset_score(_weighted(P, difficulty_weights(P, mask, "local_eq", N)), mask, model)
    else:
        s["reading"] = {"score": None, "n": 0}
    Pc = _weighted(P, Wa)
    ratio = miss_chain_ratio(Pc) if len(P) else math.nan
    s["consistency"] = {"score": _clip(50 + 30 * math.log2(TYPICAL_CHAIN_RATIO / ratio))
                        if ratio and not math.isnan(ratio) else None,
                        "n": int(len(P)), "miss_after_miss_ratio": ratio}
    misses = float((~P["head_hit"].astype(bool)).sum()) if len(P) else 0.0
    if s["consistency"]["score"] is None and len(P) >= FEW_MISSES_NOTES and misses < FEW_MISSES:
        s["consistency"]["too_few_misses"] = True        # nothing to chain: no misses to follow a miss
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


CLEAN_PASS_MISSES_PER_100 = 5.0


def clean_pass(metas: pd.DataFrame) -> pd.Series:
    """Finished plays with at most 5 misses per 100 notes: getting through a map with many more (lazer
    lets you) is no real pass of it."""
    per_100 = metas["head_misses"] / metas["n_objects"].clip(lower=1) * 100
    return metas["completed"].astype(bool) & (per_100 <= CLEAN_PASS_MISSES_PER_100)


def comfort_stars(metas: pd.DataFrame) -> float:
    """Star rating you play comfortably: 75th percentile of finished plays with at most 2 misses per 100
    notes (columns stars, head_misses, n_objects, completed)."""
    if metas.empty or "stars" not in metas:
        return math.nan
    m = metas.dropna(subset=["stars"])
    if m.empty:
        return math.nan
    m = m.assign(miss_per_100=m["head_misses"] / m["n_objects"].clip(lower=1) * 100)
    good = m[(m["miss_per_100"] <= 2.0) & (m["completed"].astype(bool))]
    if len(good):
        return float(good["stars"].quantile(0.75))
    return float(m["stars"].quantile(0.25) - 0.4)


def _levels(metas: pd.DataFrame, P: pd.DataFrame, model) -> dict:
    """Difficulty levels (star rating units) used to pick practice maps."""
    out = {"comfort_stars": math.nan, "aim_level": math.nan, "speed_level": math.nan}
    if metas.empty or "stars" not in metas:
        return out
    out["comfort_stars"] = comfort_stars(metas)
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
