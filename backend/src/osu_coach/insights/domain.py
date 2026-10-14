"""Chart-ready aggregations of a :class:`~osu_coach.profile.Profile` and of one play.

These are the numbers behind the app's charts that aren't part of the profile itself: the playfield miss
heat map, the hit-timing histogram, streams binned along the map / the session, slider misses by length
and speed, hit results by approach rate, and a weighted random sample of clicks. They used to be computed
inside the Streamlit pages; they live here so every interface (HTTP API, command line, tests) gets the
same numbers. All of them work on the profile's per-note table and respect the difficulty weights
(column ``w``).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from osu_coach.analysis.domain import ReplayAnalysis
from osu_coach.profile.domain import Profile, played_notes

# ------------------------------------------------------------------ helpers


def played(p: Profile) -> pd.DataFrame:
    """Notes that were reached in the play, without spinners."""
    return played_notes(p.objects)


def weights(df: pd.DataFrame) -> np.ndarray:
    """Difficulty weight of every row (its replay's weight), 1 if there are none."""
    return df["w"].to_numpy(float) if "w" in df else np.ones(len(df))


# ------------------------------------------------------------------ aim
PLAYFIELD_W, PLAYFIELD_H = 512, 384
GRID_COLS, GRID_ROWS = 8, 6
GRID_MIN_NOTES = 15      # cells with fewer (weighted) notes stay empty


def playfield_grid(p: Profile) -> dict:
    """Miss rate (%) on an 8 × 6 grid of the playfield as the player sees it (y down). ``rate[row][col]``,
    NaN where a cell has fewer than :data:`GRID_MIN_NOTES` notes; ``x`` / ``y`` are the cell centres."""
    P = played(p)
    bins_x, bins_y = np.linspace(0, PLAYFIELD_W, GRID_COLS + 1), np.linspace(0, PLAYFIELD_H, GRID_ROWS + 1)
    allh, _, _ = np.histogram2d(P["x"].clip(0, PLAYFIELD_W - 0.1), P["y"].clip(0, PLAYFIELD_H - 0.1),
                                bins=[bins_x, bins_y], weights=weights(P))
    M = P[~P["head_hit"]]
    mh, _, _ = np.histogram2d(M["x"].clip(0, PLAYFIELD_W - 0.1), M["y"].clip(0, PLAYFIELD_H - 0.1),
                              bins=[bins_x, bins_y], weights=weights(M))
    rate = np.where(allh >= GRID_MIN_NOTES, mh / np.maximum(allh, 1) * 100, np.nan)
    return {"x": ((bins_x[:-1] + bins_x[1:]) / 2).tolist(), "y": ((bins_y[:-1] + bins_y[1:]) / 2).tolist(),
            "rate": rate.T.tolist(), "notes": allh.T.tolist()}


CLICKS_DRAWN = 4000
CLICK_RANGE = 2.4        # radii shown around the circle centre


def click_sample(C: pd.DataFrame, n: int = CLICKS_DRAWN, seed: int = 0) -> pd.DataFrame:
    """One random sample of ``n`` clicks (of :func:`~osu_coach.profile.click_points`), so the share of aim
    misses in the picture is the real one. Plays far from the player's level are drawn less often, like
    they count less: weighted sampling without replacement (the ``n`` largest u^(1/w)). Clicks further
    than :data:`CLICK_RANGE` radii from the centre are left out."""
    if len(C) > n:
        w = C["w"].to_numpy(float) if "w" in C else np.ones(len(C))
        keys = np.log(np.random.default_rng(seed).random(len(C))) / np.maximum(w, 1e-12)
        drawn = C.iloc[np.sort(np.argsort(keys)[-n:])]
    else:
        drawn = C
    return drawn[(drawn["x"].abs() < CLICK_RANGE) & (drawn["y"].abs() < CLICK_RANGE)]


# ------------------------------------------------------------------ tapping
TIMING_RANGE_MS = 150
TIMING_BIN_MS = 3


def timing_histogram(p: Profile) -> dict:
    """Weighted hit counts per :data:`TIMING_BIN_MS` ms of hit error (real time, −150…+150 ms), one series
    per result (300 / 100 / 50), the weighted average error, each result's share of the hits and ``total`` =
    the weight of all hits shown (a bin's share of all hits = its count / total)."""
    P = played(p)
    H = P[P["head_hit"]].dropna(subset=["err_real"])
    H = H[H["err_real"].abs() <= TIMING_RANGE_MS]
    edges = np.arange(-TIMING_RANGE_MS, TIMING_RANGE_MS + TIMING_BIN_MS, TIMING_BIN_MS)
    counts, shares = {}, {}
    for res in (300, 100, 50):
        sel = H["head_result"] == res
        c, _ = np.histogram(H.loc[sel, "err_real"], bins=edges, weights=weights(H[sel]))
        counts[res] = c.tolist()
        shares[res] = float(weights(H[sel]).sum())
    scored = sum(shares.values())
    total = float(weights(H).sum())
    mean = float(np.average(H["err_real"], weights=weights(H))) if len(H) and total > 0 else math.nan
    return {"centers": ((edges[:-1] + edges[1:]) / 2).tolist(), "counts": counts, "total": total,
            "shares": {r: (v / scored if scored else math.nan) for r, v in shares.items()}, "mean": mean}


def key_hold_ms(p: Profile) -> float:
    """Median key hold in real time (ms), over all presses."""
    Pr = p.presses
    if Pr is None or not len(Pr):
        return math.nan
    rates = dict(zip(p.replays["key"], p.replays["rate"]))
    dur = (Pr["duration"] / Pr["replay_key"].map(rates).fillna(1.0)).dropna()
    return float(dur.median()) if len(dur) else math.nan


STREAM_BAND = 20         # BPM per band in "streams over time"
STREAM_BAND_MIN = 200    # notes a band needs to be offered
STREAM_MIN_NOTES = 100   # stream notes needed for the chart at all
STREAM_BIN_MIN = 30      # notes a point needs
STREAM_UR_MIN = 20       # hits a point needs for its UR
STREAM_STEPS = {"map": ("map_min", 0.5), "session": ("session_min", 5.0)}   # minutes per point
SESSION_GAP_S = 3600


def stream_notes(p: Profile) -> pd.DataFrame:
    """Stream / burst notes (7+ in a row) with the minute in the map, the minute in the session (plays less
    than an hour apart) and a :data:`STREAM_BAND`-BPM band."""
    P = played(p)
    S = P[P["pattern"].isin(["stream", "burst", "spaced"]) & P["stream_bpm"].notna() & (P["run_len"] >= 7)].copy()
    if S.empty:
        return S
    S["map_min"] = S["time"] / 60000.0
    dates = p.replays.set_index("key")["date"]
    order = dates.sort_values()
    start, last, sess = {}, None, None
    for k, d in order.items():
        if last is None or (d - last).total_seconds() > SESSION_GAP_S:
            sess = d
        start[k], last = sess, d
    S["session_min"] = [((dates[k] - start[k]).total_seconds() + t / 1000) / 60.0
                        for k, t in zip(S["replay_key"], S["time"])]
    S["band"] = (S["stream_bpm"] // STREAM_BAND * STREAM_BAND).astype(int)
    return S


def stream_bins(S: pd.DataFrame, xcol: str, step: float) -> pd.DataFrame:
    """Per time bin: weighted miss rate (%), UR (each play's own average taken out first, so different plays
    don't inflate it) and notes. ``x`` = start of the bin."""
    rows = []
    S = S.assign(xb=(S[xcol] // step * step), err0=S["err_real"] - S.groupby("replay_key")["err_real"].transform("mean"))
    for xb, g in S.groupby("xb"):
        h = g["head_hit"].astype(bool) & g["err0"].notna()
        if len(g) < STREAM_BIN_MIN:
            continue
        w = g["w"].to_numpy(float) if "w" in g else np.ones(len(g))
        miss = float(np.average(~g["head_hit"].astype(bool), weights=w)) if w.sum() else math.nan
        ur = float(np.sqrt(np.average(g.loc[h, "err0"] ** 2, weights=g.loc[h, "w"]))) * 10 \
            if h.sum() >= STREAM_UR_MIN else math.nan
        rows.append({"x": float(xb), "miss_rate": miss * 100, "ur": ur, "n": int(len(g))})
    return pd.DataFrame(rows, columns=["x", "miss_rate", "ur", "n"])


def stream_time_series(p: Profile) -> dict | None:
    """Streams over time: for all streams together (``"overall"``) and every BPM band with
    :data:`STREAM_BAND_MIN`+ notes, the bins of :func:`stream_bins` along the map and along the session.
    None with fewer than :data:`STREAM_MIN_NOTES` stream notes."""
    S = stream_notes(p)
    if S.empty or len(S) < STREAM_MIN_NOTES:
        return None
    counts = S["band"].value_counts()
    bands = sorted(int(b) for b in counts.index if counts[b] >= STREAM_BAND_MIN)
    out = {"bands": bands, "band_width": STREAM_BAND, "notes": int(len(S)), "series": {}}
    for along, (xcol, step) in STREAM_STEPS.items():
        series = {"overall": stream_bins(S, xcol, step)}
        for b in bands:
            series[str(b)] = stream_bins(S[S["band"] == b], xcol, step)
        out["series"][along] = {"step": step, "lines": series}
    return out


def fall_behind_by_speed(cb: pd.DataFrame | None) -> dict:
    """Per stream speed (``curves_bpm`` of the stamina-in-long-streams result): error at the first and last
    point (% of the time between notes), the last note measured, and the speed where it rises most."""
    if cb is None or len(cb) < 3:
        return {"groups": [], "worst": None}
    last = cb.sort_values("pos").groupby("group").agg(first=("rel_err", "first"), last=("rel_err", "last"),
                                                     notes=("pos", "max"))
    last["rise"] = last["last"] - last["first"]
    worst = last["rise"].idxmax() if len(last) else None
    groups = [{"group": str(g), "first": float(r["first"]), "last": float(r["last"]), "notes": int(r["notes"]),
               "rise": float(r["rise"])} for g, r in last.iterrows()]
    return {"groups": groups, "worst": str(worst) if worst is not None and last.loc[worst, "rise"] > 3 else None}


# ------------------------------------------------------------------ sliders & reading
SLIDER_LEN_BINS = [0, 1, 2, 4, 8, 1000]           # circle diameters of slider path
SLIDER_SPEED_BINS = [0, 2, 4, 6, 9, 1000]         # circle diameters per second
SLIDER_MIN = 100         # sliders needed for the charts
SLIDER_BIN_MIN = 20      # sliders a bar needs
SLIDER_BIG_BIN = 50      # bars with this many sliders are preferred for "worst"


def _slider_rates(S: pd.DataFrame, col: str, bins: list) -> pd.DataFrame:
    cut = pd.cut(S[col], bins, right=False)
    rows = []
    for iv, g in S.groupby(cut, observed=True):
        if len(g) < SLIDER_BIN_MIN:
            continue
        w = g["w"].to_numpy(float)
        head = ~g["head_hit"].astype(bool)
        brk = g["broke"].fillna(False).astype(bool) & ~head
        hi = "+" if iv.right >= 1000 else f"–{iv.right:g}"
        rows.append({"bin": f"{iv.left:g}{hi}", "head": float(np.average(head, weights=w)) * 100,
                     "broke": float(np.average(brk, weights=w)) * 100, "n": int(len(g))})
    return pd.DataFrame(rows, columns=["bin", "head", "broke", "n"])


def slider_rates(p: Profile) -> dict | None:
    """Slider head misses and breaks (after hitting the head, %) by slider length (circle diameters) and by
    slider speed (diameters per second), each with its worst bin. None with fewer than :data:`SLIDER_MIN`
    sliders."""
    P = played(p)
    S = P[(P["kind"] == "slider") & P["slider_len"].notna()].copy()
    if len(S) < SLIDER_MIN:
        return None
    d = (2 * S["radius"]).replace(0, np.nan)
    S["len_d"] = S["slider_len"] / d
    S["speed_d"] = S["slider_vel_real"] * 1000 / d
    out = {}
    for name, col, bins in (("length", "len_d", SLIDER_LEN_BINS), ("speed", "speed_d", SLIDER_SPEED_BINS)):
        R = _slider_rates(S, col, bins)
        worst = None
        if not R.empty:
            big = R[R["n"] >= SLIDER_BIG_BIN] if (R["n"] >= SLIDER_BIG_BIN).any() else R
            worst = big.assign(t=big["head"] + big["broke"]).sort_values("t").iloc[-1]["bin"]
        out[name] = {"rows": R, "worst": worst}
    return out


AR_MIN_NOTES = 200       # notes needed for the chart
AR_BIN_MIN = 100         # notes a bar needs


def hits_by_ar(p: Profile) -> pd.DataFrame:
    """300s / 100s / 50s / misses (% of the notes, weighted) per approach rate (with mods, in 0.5 steps)."""
    P = played(p)
    H = P[(P["kind"] != "spinner") & P["map_ar"].notna()].copy()
    cols = ["ar", "n", "plays", "300", "100", "50", "miss"]
    if len(H) < AR_MIN_NOTES:
        return pd.DataFrame(columns=cols)
    H["ar"] = np.floor(H["map_ar"].astype(float) * 2) / 2
    rows = []
    for ar, g in H.groupby("ar"):
        if len(g) < AR_BIN_MIN:
            continue
        w = g["w"].to_numpy(float)
        res = g["head_result"].where(g["head_hit"].astype(bool), 0)
        row = {"ar": float(ar), "n": int(len(g)), "plays": int(g["replay_key"].nunique())}
        for r, name in ((300, "300"), (100, "100"), (50, "50"), (0, "miss")):
            row[name] = float(np.average(res == r, weights=w)) * 100
        rows.append(row)
    return pd.DataFrame(rows, columns=cols)


# ------------------------------------------------------------------ one play
TREND_WINDOW = 25


def play_timing(a: ReplayAnalysis) -> dict | None:
    """Hit timing through one play: every hit (map time, error in real time, result), the running average
    over :data:`TREND_WINDOW` hits, and the 300 window (± ms) from the play's OD. None with fewer than 5 hits."""
    o = a.objects
    H = o[o["played"] & o["head_hit"] & (o["kind"] != "spinner")].dropna(subset=["err_real"])
    if len(H) < 5:
        return None
    trend = H["err_real"].rolling(TREND_WINDOW, center=True, min_periods=5).mean()
    od = a.meta.get("od")
    w300 = 80 - 6 * od if od is not None and not (isinstance(od, float) and math.isnan(od)) else None
    return {"time": H["time"].to_numpy(float).tolist(), "error": H["err_real"].to_numpy(float).tolist(),
            "result": H["head_result"].fillna(0).astype(int).tolist(), "trend": trend.to_numpy(float).tolist(),
            "window_300": w300, "length_ms": float(o["time"].max()),
            "top": float(H["err_real"].abs().quantile(0.99) or 50) * 1.15}
