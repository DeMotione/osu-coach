"""Per-replay analysis: judgement simulation + pattern features + difficulty.

Produces two tidy tables per replay:
* ``objects`` – one row per hit object: what it was (pattern features) and what
  the player did (judgement, timing error, aim error vector, miss reason ...);
* ``presses`` – one row per key press (key, hold duration, gaps, target).
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from osu_coach.domain import difficulty
from osu_coach.infrastructure.filesystem.beatmap import Beatmap, PlayableBeatmap, parse_beatmap_bytes
from osu_coach.domain.features import object_features
from osu_coach.domain.judge import simulate
from osu_coach.domain.judge_lazer import lazer_mod_settings
from osu_coach.infrastructure.filesystem.osr import MOD_BITS, Replay, parse_replay, mods_to_string

ANALYSIS_VERSION = 7

# lazer mods whose effect the simulation can't reproduce (speed or note positions change during the
# map, extra input rules): such replays are skipped with this reason
UNSUPPORTED_LAZER_MODS = {
    "WU": "Wind Up changes the speed during the map", "WD": "Wind Down changes the speed during the map",
    "AS": "Adaptive Speed changes the speed during the map", "RD": "Random moves the notes",
    "WG": "Wiggle moves the notes", "TR": "Transform moves the notes", "MG": "Magnetised moves the cursor",
    "RP": "Repel moves the cursor", "BR": "Barrel Roll rotates the playfield", "DP": "Depth moves the notes",
    "GR": "Grow changes the note size", "DF": "Deflate changes the note size", "SI": "Spin In changes the notes",
    "TP": "Target Practice replaces the map", "AL": "Alternate blocks some presses",
    "SG": "Single Tap blocks some presses", "ST": "Strict Tracking changes slider rules",
}


class UnsupportedReplay(ValueError):
    """A replay osu-coach can't analyse faithfully (reason in the message)."""


def playable(bm: Beatmap, replay: Replay) -> PlayableBeatmap:
    """The beatmap as it was played: legacy mods, lazer's speed changes, Difficulty Adjust and Mirror."""
    mods = lazer_mod_settings(replay)
    da = mods.get("DA") or {}
    overrides = {k: float(da[src]) for k, src in (("cs", "circle_size"), ("ar", "approach_rate"),
                                                  ("od", "overall_difficulty"), ("hp", "drain_rate"))
                 if isinstance(da.get(src), (int, float))}
    mirror = None
    if "MR" in mods:
        refl = mods["MR"].get("reflection", 0)
        mirror = {0: "horizontal", 1: "vertical", 2: "both"}.get(refl, str(refl).lower())
        if mirror not in ("horizontal", "vertical", "both"):
            mirror = "horizontal"
    return PlayableBeatmap(bm, replay.mods, rate=replay.rate, overrides=overrides or None, mirror=mirror)


@dataclass
class ReplayAnalysis:
    key: str
    meta: dict
    objects: pd.DataFrame = field(repr=False)
    presses: pd.DataFrame = field(repr=False)


def along_cross(ex: float, ey: float, mx: float, my: float) -> tuple[float, float]:
    """Split an aim error (ex, ey) into the component along the movement
    direction (positive = overshoot) and across it (positive = clockwise side
    in screen coordinates, y pointing down)."""
    n = math.hypot(mx, my)
    if n < 1e-9:
        return (math.nan, math.nan)
    ux, uy = mx / n, my / n
    along = ex * ux + ey * uy
    cross = -ex * uy + ey * ux
    return (along, cross)


def replay_key(replay: Replay, raw: bytes | None = None) -> str:
    if replay.replay_md5:
        return replay.replay_md5
    return hashlib.md5(raw or f"{replay.beatmap_md5}{replay.timestamp}{replay.score}".encode()).hexdigest()


def analyze_files(replay_path, beatmap_path) -> ReplayAnalysis:
    raw = Path(replay_path).read_bytes()
    replay = parse_replay(raw, source_path=str(replay_path))
    osu_bytes = Path(beatmap_path).read_bytes()
    return analyze(replay, osu_bytes, raw)


def analyze(replay: Replay, osu_bytes: bytes, raw_replay: bytes | None = None,
            beatmap: Beatmap | None = None) -> ReplayAnalysis:
    unsupported = [UNSUPPORTED_LAZER_MODS[m] for m in lazer_mod_settings(replay) if m in UNSUPPORTED_LAZER_MODS]
    if unsupported:
        raise UnsupportedReplay(f"skipped: {unsupported[0]}")
    bm = beatmap or parse_beatmap_bytes(osu_bytes)
    rate = replay.rate
    pb = playable(bm, replay)
    sim = simulate(pb, replay)
    feats = object_features(pb)
    key = replay_key(replay, raw_replay)

    res_rows = []
    for r in sim.objects:
        res_rows.append({
            "result": r.result, "head_hit": bool(r.head_hit), "head_result": r.head_result,
            "hit_time": r.hit_time, "hit_error": r.hit_error, "click_x": r.click_x, "click_y": r.click_y,
            "key": r.key, "press_id": r.press_id, "miss_reason": r.miss_reason, "miss_dist": r.miss_dist,
            "miss_x": r.miss_x, "miss_y": r.miss_y, "forced_miss": r.forced_miss,
            "n_events": r.n_events, "n_events_hit": r.n_events_hit, "end_hit": r.end_hit,
            "broke": r.broke, "break_reason": r.break_reason, "spins": r.spins,
            "spins_required": r.spins_required,
        })
    obj = pd.concat([feats.reset_index(drop=True), pd.DataFrame(res_rows)], axis=1)
    for col in ("hit_time", "hit_error", "click_x", "click_y", "miss_dist", "miss_x", "miss_y", "spins",
                "spins_required", "press_id"):
        obj[col] = pd.to_numeric(obj[col], errors="coerce").astype(float)
    obj["replay_key"] = key
    obj["played"] = obj["result"] >= 0
    obj["err_real"] = obj["hit_error"] / rate
    radius = pb.radius_raw
    obj["radius"] = radius

    # aim error: hits use the hitting click, aim misses the closest click
    ex = np.where(obj["head_hit"], obj["click_x"] - obj["x"], obj["miss_x"] - obj["x"])
    ey = np.where(obj["head_hit"], obj["click_y"] - obj["y"], obj["miss_y"] - obj["y"])
    obj["err_dx"] = ex
    obj["err_dy"] = ey
    obj["aim_err"] = np.hypot(ex, ey) / radius
    # movement start: cursor where the previous object was hit, else its end position
    start_x = np.full(len(obj), np.nan)
    start_y = np.full(len(obj), np.nan)
    cx = obj["click_x"].to_numpy()
    cy = obj["click_y"].to_numpy()
    for i, p in enumerate(obj["prev_idx"].to_numpy()):
        if p is None or (isinstance(p, float) and math.isnan(p)):
            continue
        p = int(p)
        if obj.at[p, "head_hit"] and obj.at[p, "kind"] == "circle" and not math.isnan(cx[p]):
            start_x[i], start_y[i] = cx[p], cy[p]
        else:
            start_x[i], start_y[i] = obj.at[p, "end_x"], obj.at[p, "end_y"]
    obj["start_x"] = start_x
    obj["start_y"] = start_y
    along = np.full(len(obj), np.nan)
    cross = np.full(len(obj), np.nan)
    for i in range(len(obj)):
        if math.isnan(ex[i]) or math.isnan(start_x[i]):
            continue
        a, c = along_cross(ex[i], ey[i], obj.at[i, "x"] - start_x[i], obj.at[i, "y"] - start_y[i])
        along[i], cross[i] = a / radius, c / radius
    obj["along"] = along
    obj["cross"] = cross

    lazer_mods = (replay.lazer or {}).get("mods") or None
    attrs = difficulty.attributes(osu_bytes, replay.mods, rate, lazer_mods=lazer_mods, lazer=replay.is_lazer)
    _attach_strains(obj, osu_bytes, replay, pb, rate, attrs)

    presses = _press_table(sim.presses, obj)
    presses["replay_key"] = key

    played = obj[obj["played"] & (obj["kind"] != "spinner")]
    hits = played[played["head_hit"]]
    errs = hits["err_real"].dropna()
    n_played = int(obj["played"].sum())
    header = (replay.n300, replay.n100, replay.n50, replay.nmiss)
    simc = (sim.counts[300], sim.counts[100], sim.counts[50], sim.counts[0])
    header_total, sim_total = sum(header), sum(simc)
    # some tools write replays without results (all zero): fall back to the simulation then
    counts = header if header_total else simc
    acc = ((300 * counts[0] + 100 * counts[1] + 50 * counts[2]) / (300 * sum(counts))) if sum(counts) else math.nan
    meta = {
        "key": key, "player": replay.player, "date": replay.timestamp, "beatmap_md5": replay.beatmap_md5,
        "title": bm.title, "artist": bm.artist, "version": bm.version_name, "creator": bm.creator,
        "beatmap_id": bm.beatmap_id, "beatmapset_id": bm.beatmapset_id, "map_name": bm.display_name,
        "mods": replay.mods, "mod_string": mods_to_string(replay.mods), "rate": rate, "rules": sim.rules,
        "client": "lazer" if replay.is_lazer else "stable", "replay_version": replay.version,
        "n300": counts[0], "n100": counts[1], "n50": counts[2], "nmiss": counts[3],
        "max_combo": replay.max_combo if header_total else sim.max_combo, "score": replay.score, "accuracy": acc,
        "header_empty": header_total == 0,
        "sim_counts": simc, "sim_max_combo": sim.max_combo,
        "sim_match": (simc == header) if header_total else None,
        "sim_agreement": (1 - sum(abs(a - b) for a, b in zip(simc, header)) / header_total) if header_total
        else math.nan,
        "n_objects": len(obj), "n_played": n_played, "completed": n_played >= len(obj) - 1,
        "cs": pb.cs, "ar": pb.effective_ar, "od": pb.effective_od, "hp": pb.hp,
        "bpm": bm.main_bpm() * rate, "length_s": bm.drain_seconds / rate,
        "ur": float(10 * errs.std(ddof=0)) if len(errs) > 1 else math.nan,
        "mean_error": float(errs.mean()) if len(errs) else math.nan,
        "head_misses": int((~played["head_hit"]).sum()),
        "relax_or_autopilot": bool(replay.mods & (MOD_BITS["RX"] | MOD_BITS["AP"] | MOD_BITS["AT"])),
        "source_path": replay.source_path, "analysis_version": ANALYSIS_VERSION,
    }
    # lazer replays also store slider tick / tail results: a second, finer check of the simulation
    stats = (replay.lazer or {}).get("statistics") or {}
    if sim.lazer_stats is not None and stats:
        for k, name in (("large_tick_hit", "ticks"), ("slider_tail_hit", "tails")):
            meta[f"sim_{name}"] = sim.lazer_stats.get(k, 0)
            meta[f"replay_{name}"] = int(stats.get(k, 0) or 0)
    for k in ("stars", "aim", "speed", "reading", "slider_factor", "speed_note_count", "max_combo"):
        if k in attrs:
            meta["map_max_combo" if k == "max_combo" else k] = attrs[k]
    return ReplayAnalysis(key, meta, obj, presses)


def _attach_strains(obj: pd.DataFrame, osu_bytes: bytes, replay: Replay, pb: PlayableBeatmap, rate: float,
                    attrs: dict | None = None):
    """Per-object local difficulty from osu!'s strain model.

    ``*_strain`` = section peak / map peak (0..1, where in the map it's hardest);
    ``*_eq`` = star-equivalent of the section: the rating a map would have if it
    were this hard all the way through, c*sqrt(10*S) with c calibrated so the
    map's own peaks reproduce its official aim/speed rating."""
    s = difficulty.strains(osu_bytes, replay.mods, rate, lazer_mods=(replay.lazer or {}).get("mods") or None,
                           lazer=replay.is_lazer)
    for col in ("aim_strain", "speed_strain", "reading_strain", "aim_eq", "speed_eq"):
        obj[col] = np.nan
    if not s or len(obj) < 2:
        return
    L = s["section_length"]
    second = obj["time"].iloc[1] / rate
    for skill in ("aim", "speed", "reading"):
        vals = s.get(skill) or []
        if not vals:
            continue
        arr = np.asarray(vals, dtype=float)
        peak = arr.max() or 1.0
        idx = np.array([difficulty.section_index(t / rate, second, L, len(arr)) for t in obj["time"]])
        obj[f"{skill}_strain"] = np.where(idx >= 0, arr[np.clip(idx, 0, None)] / peak, np.nan)
        if skill in ("aim", "speed"):
            peaks = np.sort(arr)[::-1]
            weighted = float((peaks * 0.9 ** np.arange(len(peaks))).sum())
            rating = (attrs or {}).get(skill)
            c = rating / math.sqrt(weighted) if rating and weighted > 0 else 0.066
            obj[f"{skill}_eq"] = np.where(idx >= 0, c * np.sqrt(10 * arr[np.clip(idx, 0, None)]), np.nan)


def _press_table(presses, obj: pd.DataFrame) -> pd.DataFrame:
    cols = ["id", "key", "time", "release", "duration", "x", "y", "target", "outcome"]
    if not presses:
        return pd.DataFrame(columns=cols + ["gap_prev", "same_key_gap", "alternated", "target_pattern",
                                            "target_dt", "target_run_len", "hold_ratio"])
    df = pd.DataFrame([{"id": p.id, "key": p.key, "time": p.time, "release": p.release, "duration": p.duration,
                        "x": p.x, "y": p.y, "target": p.target, "outcome": p.outcome} for p in presses])
    df = df.sort_values(["time", "id"]).reset_index(drop=True)
    df["gap_prev"] = df["time"].diff()
    df["prev_key"] = df["key"].shift(1)
    df["alternated"] = df["key"] != df["prev_key"]
    # time from the previous release of the same key to this press (re-press gap)
    gaps = []
    last_release: dict[str, float] = {}
    for k, t, rel in zip(df["key"], df["time"], df["release"]):
        lr = last_release.get(k)
        gaps.append(t - lr if lr is not None else np.nan)
        if rel is not None and not (isinstance(rel, float) and math.isnan(rel)):
            last_release[k] = rel
    df["same_key_gap"] = gaps
    tgt = df["target"]
    valid = tgt.notna()
    df["target_pattern"] = None
    df["target_dt"] = np.nan
    df["target_run_len"] = np.nan
    if valid.any():
        ti = tgt[valid].astype(int)
        df.loc[valid, "target_pattern"] = obj.loc[ti, "pattern"].to_numpy()
        df.loc[valid, "target_dt"] = obj.loc[ti, "dt"].to_numpy()
        df.loc[valid, "target_run_len"] = obj.loc[ti, "run_len"].to_numpy()
    df["hold_ratio"] = df["duration"] / df["target_dt"]
    return df
