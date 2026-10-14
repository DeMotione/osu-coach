"""Reading (AR / BPM changes): metrics, values and the reading score."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from osu_coach.profile.domain.ranking import _n_replays, ranked_mean
from osu_coach.profile.domain.stats import _clip, _map_key, _rate, _w


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


# ------------------------------------------------------------------ reading
READ_AR_STEP = 3.0  # every 3 AR below what is usual for the map's star rating doubles the reading demand
READ_AR_MIN = 1.0  # the AR factor never lowers the value
READ_AR_HIGH_STEP = 1.5  # every 1.5 AR above the usual AR doubles it too (reaction to fast approach)
READ_LOW_AR, READ_HIGH_AR = 8.0, 10.0  # sub-scores: maps below AR 8 / from AR 10
READ_NPS = 5.0  # circles per second (during play, breaks left out) at which low AR counts fully ...
READ_NPS_RANGE = (0.25, 2.0)  # ... the AR difference counts × circles per second ÷ 5 (0.25–2)
READ_HD, READ_FL = 1.2, 1.6  # hidden / flashlight hide the notes: more to read
READ_BPM_JUMP = 0.08  # a BPM change: the beat length changes by 8%+ from one note to the next
READ_BPM_NOTES = 4  # the first 4 notes after a BPM change show whether you read it
READ_BPM_FULL = 8  # 8+ BPM changes in a map = the full BPM-change bonus (×1.5 when you hit them as 300s)
READ_BPM_BONUS = 0.5
READ_ACC_POWER = 8.0  # × accuracy^8: 99% = 0.92, 95% = 0.66, 90% = 0.43, 85% = 0.27
READ_REF = 0.95**8 * 1.3  # 50 = a little above the usual AR for the map at 95% (×1.3 after review)
READ_POINTS = 25.0  # points per doubling of the value


def usual_ar(stars) -> np.ndarray:
    """The approach rate maps of this star rating (with mods) usually have: 7.25 at 3*, 9.5 at 6*, 10.5 from 7.3*."""
    return np.clip(5.0 + 0.75 * np.asarray(stars, dtype=float), 5.0, 10.5)


def reading_values(P: pd.DataFrame) -> pd.DataFrame:
    """Per passed play: reading demand × how well you played it.

    * ``ar_factor`` = 2^((usual AR for the map's stars − its AR with mods) / 3 × ``busy``): AR 3 lower than
      usual = ×2, 6 lower = ×4 on a map with 5 circles per second; ``busy`` = circles per second ÷ 5 (during
      play, breaks of 5+ s left out; 0.25–2), so low AR on a slow map (3 per second: ×0.6 of the AR difference)
      counts much less than on a busy one (higher AR than usual: down to 0.6); × 1.2 with hidden, × 1.6 with
      flashlight;
    * ``bpm_factor`` = 1 + 0.5 × min(1, BPM changes ÷ 8) × your 300 share on the first 4 notes after each
      change (a miss = 0): read and hit the BPM changes accurately and a map full of them counts ×1.5;
    * ``value`` = ar_factor × bpm_factor × accuracy^8 (decent accuracy on those maps: 95% = 0.66)."""
    cols = ["replay_key", "map", "ar", "nps", "ar_factor", "bpm_changes", "bpm_hit", "bpm_factor", "accuracy", "value"]
    if P is None or P.empty or "map_ar" not in P or "accuracy" not in P:
        return pd.DataFrame(columns=cols)
    D = P[P["kind"] != "spinner"] if "kind" in P else P
    if "completed" in D:
        D = D[D["completed"].astype(bool)]
    rows = []
    for (k, m), d in D.groupby([D["replay_key"], _map_key(D)], sort=False):
        d = d.sort_values("time")
        ar, acc = float(d["map_ar"].iloc[0]), float(d["accuracy"].iloc[0])
        if not (np.isfinite(ar) and np.isfinite(acc)) or len(d) < 30:
            continue
        stars = float(d["stars"].iloc[0]) if "stars" in d and np.isfinite(d["stars"].iloc[0]) else 6.0
        tt = d["time"].astype(float).to_numpy() / (float(d["rate"].iloc[0]) if "rate" in d else 1.0) / 1000.0
        gaps = np.diff(tt)
        active = float(gaps[(gaps > 0) & (gaps <= 5.0)].sum())
        nps = len(tt) / active if active > 0 else READ_NPS
        busy = float(np.clip(nps / READ_NPS, *READ_NPS_RANGE))
        diff = float(usual_ar(stars)) - ar
        f_ar = max(READ_AR_MIN, 2 ** (diff / READ_AR_STEP * busy), 2 ** (-diff / READ_AR_HIGH_STEP * busy))
        if "hidden" in d and bool(d["hidden"].iloc[0]):
            f_ar *= READ_HD
        if "flashlight" in d and bool(d["flashlight"].iloc[0]):
            f_ar *= READ_FL
        b = d["bpm_real"].astype(float).to_numpy() if "bpm_real" in d else np.full(len(d), np.nan)
        jump = np.r_[False, np.abs(np.diff(b)) / np.maximum(b[:-1], 1e-6) > READ_BPM_JUMP]
        starts = np.flatnonzero(jump)
        after = np.zeros(len(d), dtype=bool)
        for i in starts:
            after[i : i + READ_BPM_NOTES] = True
        res = d["head_result"].to_numpy() if "head_result" in d else np.where(d["head_hit"], 300, 0)
        hit = float((res[after] == 300).mean()) if after.any() else math.nan
        f_bpm = 1.0 + READ_BPM_BONUS * min(1.0, len(starts) / READ_BPM_FULL) * (hit if hit == hit else 0.0)
        rows.append(
            {
                "replay_key": k,
                "map": m,
                "ar": ar,
                "nps": nps,
                "ar_factor": f_ar,
                "bpm_changes": int(len(starts)),
                "bpm_hit": hit,
                "bpm_factor": f_bpm,
                "accuracy": acc,
                "value": f_ar * f_bpm * max(acc, 0.0) ** READ_ACC_POWER,
            }
        )
    return pd.DataFrame(rows, columns=cols)


def reading_score(P: pd.DataFrame, n_total: int | None = None) -> dict:
    """Reading: lower AR than usual (and HD / FL), decent accuracy on those maps, and BPM changes read and hit
    accurately (:func:`reading_values`); one value per map (best pass), weighted like osu!'s pp
    (:func:`ranked_mean`); 50 = the usual AR for the map at 95% accuracy, +25 per doubling."""
    out = {
        "score": None,
        "n": 0,
        "value": math.nan,
        "maps": 0,
        "lowest_ar": math.nan,
        "bpm_maps": 0,
        "bpm_hit": math.nan,
        "best": None,
        "low_ar_score": None,
        "high_ar_score": None,
        "low_ar_maps": 0,
        "high_ar_maps": 0,
    }
    V = reading_values(P)
    if V.empty:
        return out
    B = V.sort_values("value", ascending=False).drop_duplicates("map")
    N = n_total or _n_replays(P)
    out.update(
        n=int(len(V)),
        maps=int(len(B)),
        value=ranked_mean(B["value"].to_numpy(), N),
        lowest_ar=float(B["ar"].min()),
        bpm_maps=int((B["bpm_changes"] > 0).sum()),
        bpm_hit=float(B["bpm_hit"].dropna().mean()) if B["bpm_hit"].notna().any() else math.nan,
    )
    b = B.iloc[0]
    out["best"] = {"ar": float(b["ar"]), "accuracy": float(b["accuracy"]), "bpm_changes": int(b["bpm_changes"])}
    if len(B) >= 3:
        out["score"] = _clip(50 + READ_POINTS * math.log2(max(out["value"], 1e-6) / READ_REF))
    # the same, only on low-AR maps (below AR 8) and only on high-AR maps (AR 10+)
    for name, sel in (("low_ar", B["ar"] < READ_LOW_AR), ("high_ar", B["ar"] >= READ_HIGH_AR)):
        part = B[sel]
        out[f"{name}_maps"] = int(len(part))
        out[f"{name}_score"] = (
            _clip(50 + READ_POINTS * math.log2(max(ranked_mean(part["value"].to_numpy(), N), 1e-6) / READ_REF))
            if len(part) >= 3
            else None
        )
    return out
