"""Tapping: UR, stream speed profile, falling behind in streams, extra presses; the tapping speed score."""
from __future__ import annotations

import math
import numpy as np
import pandas as pd

from osu_coach.profile.domain.ranking import ranked_mean, _n_replays
from osu_coach.profile.domain.stamina import stamina_ref_bpm
from osu_coach.profile.domain.stats import played_notes, _clip, _map_key, _rate, _ur, _w, _wmean, _wquantile


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
    P = played_notes(O)
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
    P = played_notes(O)
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


FALL_BEHIND_MIN_START = 12   # stamina can't give in before note 12 of a 16+ note stream
SPEED_BAND = 30          # BPM per band in "stamina in long streams" by speed


def _fall_behind_by_speed(L: pd.DataFrame, Lw: pd.Series, min_notes: int) -> pd.DataFrame:
    """Like the length curves of :func:`stream_fall_behind`, but per 30-BPM stream speed band, with the error as a
    share of the time between notes (``rel_err``, %): 15 ms off is 20% of the gap at 200 BPM but 25% at 250, so
    faster streams aren't simply "worse"; the line's rise shows stamina at that speed."""
    cols = ["group", "pos", "rel_err", "abs_err", "miss_rate", "n"]
    if L.empty or "stream_bpm" not in L:
        return pd.DataFrame(columns=cols)
    bpm = L["stream_bpm"].astype(float)
    band = (bpm // SPEED_BAND * SPEED_BAND).astype("Int64")
    gap = 15000.0 / bpm.clip(lower=60)
    rows = []
    for b in sorted(band.dropna().unique()):
        sel = band == b
        G, Gw, Gg = L[sel], Lw[sel], gap[sel]
        pos_bin = G["run_pos"] // STREAM_BIN * STREAM_BIN
        for pb, idx in G.groupby(pos_bin).groups.items():
            d, dw, dg = G.loc[idx], Gw.loc[idx], Gg.loc[idx]
            h = d["head_hit"].astype(bool) & d["err_real"].notna()
            if h.sum() < min_notes:
                continue
            rows.append({"group": f"{int(b)}–{int(b) + SPEED_BAND - 1} BPM", "pos": int(pb) + 1,
                         "rel_err": _wmean(d.loc[h, "err_real"].abs() / dg[h] * 100, dw[h]),
                         "abs_err": _wmean(d.loc[h, "err_real"].abs(), dw[h]),
                         "miss_rate": _rate(~d["head_hit"], dw), "n": int(h.sum())})
    return pd.DataFrame(rows, columns=cols)


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
           "reach_bpm": reach_bpm,
           "curves_bpm": pd.DataFrame(columns=["group", "pos", "rel_err", "abs_err", "miss_rate", "n"])}
    if O is None or O.empty or "run_len" not in O:
        return out
    P = played_notes(O)
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
    out["curves_bpm"] = _fall_behind_by_speed(L, Lw, min_notes)
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
        if k < FALL_BEHIND_MIN_START:     # the first notes of a stream are not stamina
            continue
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
    P = played_notes(O)
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
