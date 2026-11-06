"""Practice map pool logic: per-difficulty pattern statistics + skill scores,
map suggestions and staged "improve a skill" playlists. Loading the pool file lives in
``osu_coach.infra.map_pool``."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

import numpy as np

from osu_coach.domain.beatmaps.features import MapObjects, object_features
from osu_coach.domain.beatmaps.models import Beatmap, PlayableBeatmap
from osu_coach.domain.numeric.values import finite_or_none
from osu_coach.domain.player.profile import Profile

QUADRANTS = ["top-left", "top-right", "bottom-left", "bottom-right"]
SKILLS = ["aim", "flow_aim", "speed", "stamina", "accuracy", "sliders", "reading", "consistency"]
PLAYLIST_SKILLS = SKILLS + ["quadrant", "general"]  # the skills a playlist can be made for

SKILL_INFO = {
    "aim": {"label": "Jump aim", "offset": 0.0, "focus": "landing on the centre of each circle"},
    "flow_aim": {"label": "Flow aim (spaced streams)", "offset": 0.0, "focus": "smooth, continuous cursor movement"},
    "speed": {"label": "Tapping speed (bursts/streams)", "offset": 0.0, "focus": "even, strictly alternating taps"},
    "stamina": {"label": "Stamina", "offset": -0.3, "focus": "keeping the tempo until the stream ends"},
    "accuracy": {"label": "Accuracy (timing)", "offset": -0.7, "focus": "300s — tap exactly with the music"},
    "sliders": {"label": "Slider control", "offset": -0.5, "focus": "following the ball until the slider ends"},
    "reading": {"label": "Reading (dense parts / AR)", "offset": -0.3, "focus": "looking ahead at the next notes"},
    "consistency": {"label": "Consistency", "offset": -0.5, "focus": "keeping performance steady throughout the map"},
    "quadrant": {"label": "Weak quadrant", "offset": -0.2, "focus": "committing to the full movement into the corner"},
    "general": {"label": "Level up", "offset": 0.3, "focus": "passing slightly harder maps"},
}
STAGES = [("Warm-up", -0.6), ("Core", 0.0), ("Push", 0.5)]


def finite_or(v, default=math.nan) -> float:
    value = finite_or_none(v)
    return default if value is None else value


def _c(v, lo: float, hi: float) -> float:
    """Clamp-normalise v from [lo, hi] to [0, 1]; NaN/None -> 0."""
    v = finite_or(v)
    if math.isnan(v):
        return 0.0
    return float(min(1.0, max(0.0, (v - lo) / (hi - lo))))


def _isin(texts: np.ndarray, values: tuple[str, ...]) -> np.ndarray:
    return np.fromiter((t in values for t in texts.tolist()), dtype=bool, count=len(texts))


def _median(values) -> float:
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    return float(np.median(v)) if len(v) else math.nan


def _mean(values) -> float:
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    return float(v.mean()) if len(v) else math.nan


def pattern_stats(
    bm: Beatmap, osu_bytes: bytes, mods: int = 0, rate: float | None = None, features: MapObjects | None = None
) -> dict | None:
    """Map geometry and rate-dependent pattern statistics shared by HD variants."""
    if bm.mode != 0 or len(bm.objects) < 30:
        return None
    pb = PlayableBeatmap(bm, mods, rate=rate)
    f = object_features(pb) if features is None else features
    ns = f.take(f.kind != "spinner")
    if not len(ns):
        return None
    pat = ns.pattern
    jumps = ns.take(_isin(pat, ("jump", "spaced")))
    flow = ns.take(ns.spaced_stream)
    streams = ns.take(ns.run_len >= 9)
    bursts = ns.take((ns.run_len >= 3) & (ns.run_len < 9))
    sliders = ns.take(ns.kind == "slider")
    runs = ns.take((ns.run_id >= 0) & (ns.run_len >= 3))
    ids = np.unique(runs.run_id)
    run_sizes = np.array([runs.run_len[runs.run_id == r][0] for r in ids])
    run_bpms = np.array([_median(runs.stream_bpm[runs.run_id == r]) for r in ids])
    run_bpms = np.sort(run_bpms[~np.isnan(run_bpms)])[::-1]
    run_start = np.array([runs.time[runs.run_id == r].min() for r in ids])
    run_end = np.array([runs.time[runs.run_id == r].max() for r in ids])
    run_rests = (run_start[1:] - run_end[:-1]) / pb.rate / 1000 if len(ids) > 1 else np.array([])
    rhythm = [r for r in ns.rhythm.tolist() if r is not None and r != "break"]
    kinds = ns.kind
    s = {
        "md5": hashlib.md5(osu_bytes).hexdigest(),
        "title": bm.title,
        "artist": bm.artist,
        "version": bm.version_name,
        "creator": bm.creator,
        "beatmap_id": bm.beatmap_id,
        "beatmapset_id": bm.beatmapset_id,
        "cs": pb.cs,
        "ar": pb.effective_ar,
        "od": pb.effective_od,
        "hp": pb.hp,
        "hit300_ms": (pb.hit300 - 0.5) / pb.rate,
        "hit100_ms": (pb.hit100 - 0.5) / pb.rate,
        "hit50_ms": (pb.hit50 - 0.5) / pb.rate,
        "bpm": bm.main_bpm() * pb.rate,
        "drain_length": bm.drain_seconds / pb.rate,
        "n_objects": len(f),
        "circle_share": float((kinds == "circle").mean()),
        "slider_share": float((kinds == "slider").mean()),
        "stream_share": float((pat == "stream").mean()),
        "burst_share": float((pat == "burst").mean()),
        "jump_share": float((pat == "jump").mean()),
        "spaced_share": float((pat == "spaced").mean()),
        "spaced_stream_share": float(ns.spaced_stream.mean()),
        "stream_bpm": _median(streams.stream_bpm),
        "burst_bpm": _median(bursts.stream_bpm),
        "speed_bpm": finite_or(run_bpms[2]) if len(run_bpms) >= 3 else math.nan,
        "speed_runs": int(len(run_bpms)),
        "max_run": int(ns.run_len.max()),
        "run_duration_p90": finite_or(np.quantile((run_end - run_start) / pb.rate / 1000, 0.9))
        if len(ids)
        else math.nan,
        "run_rest_median": finite_or(np.median(run_rests)) if len(run_rests) else math.nan,
        "long_runs": int((run_sizes >= 16).sum()),
        "stream_notes": len(streams),
        "n_jumps": len(jumps),
        "jump_dist": _median(jumps.dist_norm),
        "jump_velocity": _median(jumps.velocity_real),
        "flow_velocity": _median(flow.velocity_real),
        "flow_turn_share": _mean((180 - np.clip(flow.angle, 0, 180)) / 180),
        "sharp_share": float((jumps.angle < 60).mean()) if (~np.isnan(jumps.angle)).any() else math.nan,
        "slider_velocity": _median(sliders.slider_vel_real),
        "slider_length_norm": _median(sliders.slider_len / (2 * pb.radius_raw)),
        "slider_turn": _median(sliders.slider_turn),
        "slider_transition": _median(sliders.slider_next_gap),
        "reverse_share": float((sliders.slider_spans > 1).mean()) if len(sliders) else 0.0,
        "density_p90": finite_or(np.quantile(ns.density, 0.9)),
        "density_median": _median(ns.density),
        "odd_rhythm_share": float(np.mean([r in ("1/3", "1/6", "1/8", "other") for r in rhythm])) if rhythm else 0.0,
    }
    for q in QUADRANTS:
        s["q_" + q.replace("-", "_")] = float((jumps.quadrant == q).mean()) if len(jumps) else 0.0
    return s


def skill_scores(s: dict) -> dict:
    """How useful a map is for training each skill, 0..1 (heuristics on pattern stats)."""
    aim, speed = finite_or(s.get("aim"), 0.0), finite_or(s.get("speed"), 0.0)
    aim_ratio = aim / (aim + speed) if aim + speed > 0 else 0.5
    jumpy = finite_or(s.get("jump_share"), 0) + 0.5 * finite_or(s.get("spaced_share"), 0)
    tappy = finite_or(s.get("stream_share"), 0) + 0.6 * finite_or(s.get("burst_share"), 0)
    return {
        "s_aim": 0.6 * _c(jumpy, 0.05, 0.40) + 0.4 * _c(aim_ratio, 0.45, 0.60),
        "s_flow_aim": _c(s.get("spaced_stream_share"), 0.02, 0.20),
        "s_speed": 0.7 * _c(tappy, 0.05, 0.40) + 0.3 * _c(1 - aim_ratio, 0.40, 0.55),
        "s_stamina": 0.5 * _c(s.get("stream_notes"), 50, 400)
        + 0.3 * _c(s.get("max_run"), 12, 48)
        + 0.2 * _c(s.get("drain_length"), 90, 300),
        "s_accuracy": 0.5 * _c(s.get("od"), 6.5, 9.5)
        + 0.3 * _c(s.get("circle_share"), 0.3, 0.8)
        + 0.2 * (1 - _c(jumpy, 0.1, 0.5)),
        "s_sliders": 0.45 * _c(s.get("slider_share"), 0.25, 0.65)
        + 0.35 * _c(1 - finite_or(s.get("slider_factor"), 1.0), 0, 0.08)
        + 0.2 * _c(s.get("reverse_share"), 0.05, 0.35),
        "s_reading": 0.6 * _c(s.get("density_p90"), 4, 10) + 0.4 * _c(s.get("odd_rhythm_share"), 0.0, 0.15),
        "s_consistency": 0.5 * _c(s.get("drain_length"), 90, 270) + 0.5 * _c(s.get("evenness"), 0.3, 0.7),
    }


# ------------------------------------------------------------------ targets & suggestions
@dataclass
class Targets:
    comfort: float = 2.5  # star rating the player handles comfortably
    stream_bpm: float | None = None  # stream speed to train at (1/4 notes)
    quadrant: str | None = None  # weakest quadrant (if significant)
    ar_range: tuple[float, float] | None = None
    played: frozenset = field(default_factory=frozenset)


def targets_from_profile(p: Profile) -> Targets:
    lv = p.levels
    comfort = finite_or(lv.level_stars)  # detected (or chosen) level, else comfort
    if math.isnan(comfort):
        comfort = finite_or(lv.comfort_stars)
    if math.isnan(comfort):
        comfort = finite_or(p.overview.avg_stars) - 0.5
    if math.isnan(comfort):
        comfort = 2.5
    comfort = float(min(8.0, max(1.0, comfort)))
    tap = p.tapping
    bpm = tap.comfort_bpm
    if bpm is None and tap.limit_bpm:
        bpm = tap.limit_bpm - 20
    stream_bpm = float(bpm) + 10 if bpm else None
    wq = p.worst_quadrant
    quadrant = wq.quadrant if wq and wq.significant else None
    rd = p.reading
    # difficulty-adjusted (observed / expected misses) when available, raw miss rates otherwise
    adjusted = not math.isnan(finite_or(rd.mid_ar_ratio))
    key = "_ratio" if adjusted else "_miss_rate"
    hi, mid, lo = (finite_or(getattr(rd, k + key)) for k in ("high_ar", "mid_ar", "low_ar"))
    factor = 1.3 if adjusted else 1.5
    ar_range = None
    if not math.isnan(hi) and not math.isnan(mid) and mid > 0 and hi >= factor * mid:
        ar_range = (9.0, 9.7)
    elif not math.isnan(lo) and not math.isnan(mid) and mid > 0 and lo >= factor * mid:
        ar_range = (5.0, 8.0)
    played = frozenset(str(m.beatmap_md5) for m in p.replays if m.beatmap_md5 is not None)
    return Targets(comfort=comfort, stream_bpm=stream_bpm, quadrant=quadrant, ar_range=ar_range, played=played)


def map_url(r) -> str:
    bid, sid = int(finite_or(r.get("beatmap_id"), 0)), int(finite_or(r.get("beatmapset_id"), 0))
    if sid and bid:
        return f"https://osu.ppy.sh/beatmapsets/{sid}#osu/{bid}"
    return f"https://osu.ppy.sh/b/{bid}" if bid else ""


def skill_label(skill: str, t: Targets | None = None) -> str:
    if skill == "quadrant" and t and t.quadrant:
        return f"Weak quadrant ({t.quadrant})"
    return SKILL_INFO.get(skill, {"label": skill})["label"]


def collection_name(skill: str, t: Targets) -> str:
    return f"osu-coach: {skill_label(skill, t)} ({t.comfort:.1f}★)"
