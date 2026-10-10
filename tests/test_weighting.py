"""Difficulty weighting, the speed-aim miss cause, stamina / stream speed on reachable streams, the
fall-behind analysis, and replay selection (date windows, Best replays)."""
import datetime as dt
import math

import numpy as np
import pandas as pd
import pytest

from osu_coach import selection
from osu_coach.analysis import analyze_files
from osu_coach.profile import (build_profile, detect_level, miss_causes, replay_weight, stamina_score,
                               stream_fall_behind, stream_limits, stream_speed_profile)
from tests.conftest import replay_and_map
from osu_coach.pool import Targets, load_pool, stream_length_maps
from osu_coach.profile import stamina_ref_bpm


# ------------------------------------------------------------------ weights
def test_weight_is_one_inside_the_band_and_fades_outside():
    w = replay_weight([6.2, 6.6, 5.7, 7.2, 5.2, 8.2, 9.2, 3.2], 6.2)
    assert w[:3] == pytest.approx([1, 1, 1])
    assert w[3] == pytest.approx(math.exp(-0.5), rel=1e-6)      # 1★ above: 0.61
    assert w[4] == pytest.approx(w[3])                         # symmetric
    assert w[5] < 0.02                                         # 2★ off: ~0.01
    assert w[6] < 1e-3 and w[7] < 1e-3                         # 3★ off: no real effect
    assert (np.diff(replay_weight([6.7, 7.0, 7.5, 8.0], 6.2)) < 0).all()   # smooth decay


def test_unknown_stars_or_level_count_fully():
    assert replay_weight([np.nan, 5.0], 6.0)[0] == 1.0
    assert (replay_weight([3.0, 9.0], math.nan) == 1).all()


def _metas(rows):
    return pd.DataFrame([{"stars": s, "date": d, "head_misses": m, "n_objects": 100, "completed": True}
                         for s, d, m in rows])


def test_level_comes_from_recent_replays():
    now = dt.datetime(2026, 10, 10, tzinfo=dt.timezone.utc)
    old = [(7.5, now - dt.timedelta(days=400 + i), 0) for i in range(30)]       # years ago: 7.5★ clean
    new = [(6.0 + 0.01 * i, now - dt.timedelta(days=i), 1) for i in range(20)]  # this month: ~6★ clean
    lv = detect_level(_metas(old + new))
    assert lv["recent_n"] == 20
    assert lv["level"] == pytest.approx(6.14, abs=0.05)


def test_level_uses_the_newest_15_when_few_recent():
    now = dt.datetime(2026, 10, 10, tzinfo=dt.timezone.utc)
    rows = [(5.0, now - dt.timedelta(days=100 * i), 0) for i in range(40)]
    assert detect_level(_metas(rows))["recent_n"] == 15


@pytest.fixture(scope="module")
def analyses():
    names = ["circlecore__legit__legit-12.osr", "osrparse__resources__replay.osr",
             "circlecore__low_frametime_old__replay-osu_24722_433541214.osr"]
    return [analyze_files(*replay_and_map(n)[:2]) for n in names]


def test_level_override_drives_the_weights(analyses):
    stars = [a.meta["stars"] for a in analyses]
    target = stars[0]
    p = build_profile(analyses, level=target)
    assert p.levels["level_stars"] == target and p.levels["level_override"]
    assert p.replays["weight"].to_numpy() == pytest.approx(replay_weight(stars, target))
    assert p.replays["weight"].iloc[0] == 1.0
    # a replay far from the level hardly counts: weighted misses follow the replay weights
    far = build_profile(analyses, level=target + 20)
    assert far.overview["weighted_replays"] < 0.01
    assert sum(far.miss_breakdown.values()) < 0.01 * sum(far.miss_breakdown_raw.values())


# ------------------------------------------------------------------ miss causes
def test_aim_misses_on_fast_patterns_are_speed_aim():
    O = pd.DataFrame({
        "head_hit": [False, False, False, False, False, True],
        "miss_reason": ["aim", "aim", "aim", "no_tap", "aim", None],
        "run_len": [12, 1, 1, 12, 3, 12],
        "pattern": ["stream", "jump", "jump", "stream", "burst", "stream"],
        "dt_real": [60.0, 300.0, 110.0, 60.0, 80.0, 60.0],
    })
    got = [None if pd.isna(c) else c for c in miss_causes(O)]
    assert got == ["speed_aim", "aim", "speed_aim", "no_tap", "speed_aim", None]


def _streams(rows):
    out = []
    for bpm, n, miss_every, reason in rows:
        for i in range(n):
            miss = miss_every and i % miss_every == 0
            out.append({"run_len": 20, "run_pos": 1 + i % 19, "stream_bpm": bpm + 2, "head_hit": not miss,
                        "miss_reason": reason if miss else None, "err_real": 5.0, "played": True, "kind": "circle",
                        "head_result": 300, "pattern": "stream"})
    return pd.DataFrame(out)


def test_stream_speed_ignores_aim_misses():
    """Spaced DT streams where the cursor falls behind don't lower the tapping speed."""
    O = _streams([(200, 200, 0, None), (240, 200, 10, "aim"), (260, 200, 8, "no_tap")])
    prof = stream_speed_profile(O)
    row = prof.set_index("bpm_bin").loc[240]
    assert row["miss_rate"] == pytest.approx(0.1)
    assert row["tap_miss_rate"] == 0 and row["speed_aim_rate"] == pytest.approx(0.1)
    lim = stream_limits(prof, base_ur=math.nan)
    assert lim == {"comfort_bpm": 240, "limit_bpm": 260}


def _stamina_runs(spec, completed=True, key="r"):
    """spec: list of (notes, bpm, outcome per note fn(pos) -> (head_hit, miss_reason))."""
    rows = []
    for rid, (notes, bpm, outcome) in enumerate(spec):
        for pos in range(notes):
            hit, reason = outcome(pos)
            rows.append({"run_id": rid, "run_len": notes, "run_pos": pos, "stream_bpm": float(bpm), "head_hit": hit,
                         "miss_reason": reason, "replay_key": key, "completed": completed, "played": True,
                         "kind": "circle"})
    return rows


CLEAN = lambda pos: (True, None)                                                    # noqa: E731
SLOPPY = lambda pos: (pos < 20 or pos % 3 != 0, None if pos < 20 or pos % 3 else "late")   # noqa: E731
GAVE_UP = lambda pos: (pos < 20, None if pos < 20 else "no_tap")                    # noqa: E731


def test_stamina_counts_streams_you_keep_tapping_even_when_accuracy_drops():
    sloppy = pd.DataFrame(_stamina_runs([(48, 240, SLOPPY)] * 5))
    gave_up = pd.DataFrame(_stamina_runs([(48, 240, GAVE_UP)] * 5))
    a, b = stamina_score(sloppy, level=6.0), stamina_score(gave_up, level=6.0)
    assert a["streams_kept"] == 5 and b["streams_kept"] == 0
    assert a["best_stream"] == {"notes": 48, "bpm": 240.0, "load": pytest.approx(48 * 1.2 ** 3), "steady": 1.0}
    assert a["score"] is not None and a["score"] > 60
    assert b["stream_score"] is None and (b["score"] is None or b["score"] < a["score"])


def test_stamina_weighs_faster_streams_much_more():
    slow = stamina_score(pd.DataFrame(_stamina_runs([(32, 200, CLEAN)] * 5)), level=6.0)
    fast = stamina_score(pd.DataFrame(_stamina_runs([(32, 240, CLEAN)] * 5)), level=6.0)
    assert fast["stream_score"] - slow["stream_score"] == pytest.approx(25 * math.log2(1.2 ** 3), abs=0.01)
    assert stamina_ref_bpm(6.0) == 210 and stamina_ref_bpm(3.0) == 165
    # 50 = 32-note streams at the speed typical for the level
    assert stamina_score(pd.DataFrame(_stamina_runs([(32, 210, CLEAN)] * 5)), level=6.0)["stream_score"] == \
        pytest.approx(50)


def test_stamina_longer_finished_maps_load_more_failed_ones_dont_count():
    short = _stamina_runs([(16, 220, CLEAN)] * 4, key="a")
    long_ = _stamina_runs([(16, 220, CLEAN)] * 20, key="b")
    failed = _stamina_runs([(16, 220, CLEAN)] * 60, key="c", completed=False)
    s1 = stamina_score(pd.DataFrame(short), level=6.0)
    s2 = stamina_score(pd.DataFrame(short + long_ + failed), level=6.0)
    assert s2["best_play"]["replay_key"] == "b" and s2["best_play"]["stream_notes"] == 320
    assert s2["map_score"] > s1["map_score"]
    assert s2["stream_score"] == pytest.approx(s1["stream_score"])     # same streams, only the maps differ


# ------------------------------------------------------------------ stamina inside streams (precision)
def _long_streams(n_runs, length, err_fn, seed=3, bpm=200.0):
    rng = np.random.default_rng(seed)
    rows = []
    for run in range(n_runs):
        for pos in range(length):
            size = err_fn(pos) + abs(rng.normal(0, 1))
            rows.append({"run_len": length, "run_pos": pos, "run_id": run, "replay_key": "r", "head_hit": True,
                         "err_real": size * (1 if rng.random() < 0.5 else -1),   # early and late alike
                         "stream_bpm": bpm, "played": True, "kind": "circle"})
    return pd.DataFrame(rows)


def test_stamina_onset_uses_absolute_error_not_the_average():
    """Early and late taps cancel in the plain average (≈ 0 ms); the absolute error shows the precision
    falling apart after note 21 (10 ms → 50 ms)."""
    O = _long_streams(80, 48, lambda pos: 10.0 if pos < 20 else 10.0 + 1.5 * (pos - 20))
    fb = stream_fall_behind(O)
    assert abs(fb["curve"]["err"].mean()) < 3                       # the signed average says nothing
    assert fb["start_note"] == pytest.approx(21, abs=1)              # note numbers count from 1
    assert fb["base_ms"] == pytest.approx(10.8, abs=1.0)
    assert fb["comfort_notes"] == fb["start_note"]
    assert fb["practice_notes"] == (fb["start_note"], max(fb["start_note"] + 8, round(fb["start_note"] * 1.5)))
    assert fb["start_seconds"] == pytest.approx((fb["start_note"] - 1) * 15 / 200)
    assert fb["streams"] == 80 and set(fb["curves"]["group"]) == {"32–63 notes"}


def test_stamina_holds_when_precision_stays_flat():
    fb = stream_fall_behind(_long_streams(60, 40, lambda pos: 12.0, seed=4))
    assert fb["start_note"] is None and fb["comfort_notes"] == 40 and fb["practice_notes"] == (40, 60)


def test_stamina_onset_ignores_streams_out_of_reach():
    """270 BPM streams are imprecise from the start; with the reach rule they don't count."""
    slow = _long_streams(60, 32, lambda pos: 10.0, seed=5, bpm=200.0)
    fast = _long_streams(60, 32, lambda pos: 10.0 + 3 * pos, seed=6, bpm=270.0)
    fast["replay_key"] = "f"
    O = pd.concat([slow, fast], ignore_index=True)
    assert stream_fall_behind(O)["start_note"] is not None
    fb = stream_fall_behind(O, reach_bpm=210)
    assert fb["start_note"] is None and fb["bpm"] == pytest.approx(200)


# ------------------------------------------------------------------ UR by stream speed
def _plays_at(bpm, ur, offsets, n=60, seed=0):
    """``len(offsets)`` plays at one stream speed, each with UR ``ur`` around its own average offset."""
    rng = np.random.default_rng(seed)
    rows = []
    for k, off in enumerate(offsets):
        e = rng.normal(0, 1, n)
        e = (e - e.mean()) / e.std() * ur / 10 + off
        rows += [{"run_len": 20, "run_pos": 1 + i % 19, "stream_bpm": bpm + 2, "head_hit": True, "miss_reason": None,
                  "err_real": float(x), "played": True, "kind": "circle", "head_result": 300, "pattern": "stream",
                  "replay_key": f"{bpm}-{k}"} for i, x in enumerate(e)]
    return rows


def test_stream_ur_is_measured_per_play():
    """Two 100 UR plays with averages 20 ms apart pool to ~140 UR; per play it stays 100."""
    prof = stream_speed_profile(pd.DataFrame(_plays_at(200, 100, [-10, 10]))).set_index("bpm_bin")
    assert prof.loc[200, "ur"] == pytest.approx(100, abs=1) and prof.loc[200, "ur_best"] == pytest.approx(100, abs=1)
    assert prof.loc[200, "ur_pooled"] == pytest.approx(141, abs=3) and prof.loc[200, "ur_plays"] == 2


def test_stream_ur_trend_rises_and_marks_weak_speeds():
    rows = []
    for i, bpm in enumerate(range(180, 270, 10)):
        ur = 100 + 2 * (bpm - 180) + (150 if bpm == 200 else 0)     # 200 BPM sticks out
        rows += _plays_at(bpm, ur, [0, 5, -5], seed=i)
    prof = stream_speed_profile(pd.DataFrame(rows)).set_index("bpm_bin")
    assert list(prof.index[prof["weak"]]) == [200]
    assert prof.loc[250, "ur_trend"] > prof.loc[180, "ur_trend"]           # rises with speed
    assert prof.loc[220, "ur_trend"] == pytest.approx(180, abs=8)         # not pulled up by the weak speed


def test_stream_length_maps_pick_streams_of_that_length():
    pool = load_pool()
    t = Targets(comfort=6.0, stream_bpm=220.0)
    maps = stream_length_maps(pool, t, 32, 48, n=5)
    assert 0 < len(maps) <= 5
    full = pool.set_index("md5").loc[maps["md5"]]
    assert full["max_run"].between(32, 48).all()
    assert maps["why"].str.contains("longest stream").all()


# ------------------------------------------------------------------ selection
UTC = dt.timezone.utc


def _meta(md5, rate, score, acc, completed=True, key=None):
    return {"beatmap_md5": md5, "rate": rate, "score": score, "accuracy": acc, "completed": completed,
            "key": key or f"{md5}-{rate}-{score}"}


def test_best_replays_one_per_map_and_speed():
    plays = [_meta("a", 1.0, 500, 0.95), _meta("a", 1.0, 700, 0.90), _meta("a", 1.5, 300, 0.80),
             _meta("a", 1.0, 900, 0.99, completed=False),          # failed: never "best"
             _meta("b", 1.0, 400, 0.97), _meta("b", 1.0, 400, 0.98), _meta("c", 0.75, 0, 0.5, completed=False)]
    best = selection.best_replays(plays)
    got = {(m["beatmap_md5"], m["rate"]): (m["score"], m["accuracy"]) for m in best}
    assert got == {("a", 1.0): (700, 0.90), ("a", 1.5): (300, 0.80), ("b", 1.0): (400, 0.98)}
    assert selection.select(plays, "all") == plays


def test_last_session_is_the_newest_run_of_close_plays():
    t = dt.datetime(2026, 10, 7, 20, 0, tzinfo=UTC)
    times = [t, t + dt.timedelta(minutes=40), t + dt.timedelta(minutes=70),     # one session
             t - dt.timedelta(hours=5), t - dt.timedelta(days=2)]
    assert selection.last_session_start(times) == t
    since, until = selection.date_window("session", [x.isoformat() for x in times])
    assert since == t and until is None


def test_date_windows():
    now = dt.datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    assert selection.date_window("all", now=now) == (None, None)
    assert selection.date_window("7d", now=now)[0] == now - dt.timedelta(days=7)
    assert selection.date_window("30d", now=now)[0] == now - dt.timedelta(days=30)
    since, until = selection.date_window("custom", start=dt.date(2026, 10, 1), end=dt.date(2026, 10, 2), tz=UTC)
    assert since == dt.datetime(2026, 10, 1, tzinfo=UTC) and until == dt.datetime(2026, 10, 3, tzinfo=UTC)


def test_filter_refs_by_header_time():
    refs = [{"timestamp": "2026-10-09T21:00:00"}, {"timestamp": "2026-09-01T10:00:00"}, {"timestamp": ""}]
    since = dt.datetime(2026, 10, 1, tzinfo=UTC)
    assert selection.filter_refs(refs, since, None) == refs[:1]
    assert selection.filter_refs(refs, None, None) == refs
    assert selection.filter_refs(refs, None, since) == refs[1:2]


# ------------------------------------------------------------------ stamina: rhythm, overstreaming, time
def _timed_streams(spec, key="t", completed=True, gap_s=4.0):
    """spec: list of (notes, bpm, tap_gap(pos, gap_ms) -> ms until the next tap). Streams follow each other
    with ``gap_s`` seconds in between. Returns (objects, presses) like an analysis."""
    objs, prs, t = [], [], 1000.0
    for rid, (notes, bpm, tap) in enumerate(spec):
        gap = 15000.0 / bpm
        tp = t
        for pos in range(notes):
            objs.append({"run_id": rid, "run_len": notes, "run_pos": pos, "stream_bpm": float(bpm), "head_hit": True,
                         "miss_reason": None, "replay_key": key, "completed": completed, "played": True,
                         "kind": "circle", "time": t + pos * gap, "rate": 1.0})
            prs.append({"replay_key": key, "time": tp})
            tp += tap(pos, gap)
        t += notes * gap + gap_s * 1000
    return pd.DataFrame(objs), pd.DataFrame(prs)


WITH_NOTES = lambda pos, gap: gap                                                    # noqa: E731
OVERSTREAM = lambda pos, gap: gap * 0.85                                             # noqa: E731
SLOWS_DOWN = lambda pos, gap: gap if pos < 24 else gap * 1.25                        # noqa: E731
UNEVEN_LR = lambda pos, gap: gap * (0.8 if pos % 2 else 1.2)                         # noqa: E731


def test_stamina_rhythm_steady_when_tapping_with_the_notes():
    O, Pr = _timed_streams([(48, 220, WITH_NOTES)] * 5)
    s = stamina_score(O, level=6.0, presses=Pr)
    assert s["steadiness"] == pytest.approx(1.0) and s["streams_slowed"] == 0


def test_stamina_overstreaming_is_not_bad_stamina():
    """Tapping 15% faster than the notes the whole stream long: overstreaming, not tired fingers."""
    steady = stamina_score(*_args(_timed_streams([(48, 220, WITH_NOTES)] * 5)))
    over = stamina_score(*_args(_timed_streams([(48, 220, OVERSTREAM)] * 5)))
    assert over["streams_overstreamed"] == 5 and over["streams_slowed"] == 0
    assert over["score"] == pytest.approx(steady["score"])


def test_stamina_uneven_but_regular_alternation_is_steady():
    s = stamina_score(*_args(_timed_streams([(48, 220, UNEVEN_LR)] * 5)))
    assert s["steadiness"] == pytest.approx(1.0)


def test_stamina_slowing_down_in_the_second_half_costs_load():
    steady = stamina_score(*_args(_timed_streams([(48, 220, WITH_NOTES)] * 5)))
    tired = stamina_score(*_args(_timed_streams([(48, 220, SLOWS_DOWN)] * 5)))
    assert tired["streams_slowed"] == 5 and tired["steadiness"] < 0.7
    assert tired["score"] < steady["score"] - 10


def test_stamina_much_streaming_in_30_seconds_scores_higher_than_the_same_spread_out():
    dense = stamina_score(*_args(_timed_streams([(32, 220, WITH_NOTES)] * 6, gap_s=1.0)))
    spread = stamina_score(*_args(_timed_streams([(32, 220, WITH_NOTES)] * 6, gap_s=20.0)))
    assert dense["window_load"] > 2 * spread["window_load"]
    assert dense["map_load"] == pytest.approx(spread["map_load"])      # same streams, same map total
    assert dense["score"] > spread["score"]


def test_stamina_without_presses_still_scores_from_kept_streams():
    O, _ = _timed_streams([(48, 220, WITH_NOTES)] * 5)
    s = stamina_score(O, level=6.0)
    assert s["score"] is not None and math.isnan(s["steadiness"])


def _args(op):
    O, Pr = op
    return O, None, 6.0, Pr
