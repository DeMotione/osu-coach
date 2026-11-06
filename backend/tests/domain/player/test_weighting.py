"""Difficulty weighting, the speed-aim miss cause, stamina / stream speed on reachable streams, the
fall-behind analysis, and replay selection (date windows, Best replays)."""

import datetime as dt
import math

import numpy as np
import pandas as pd
import pytest

from osu_coach.domain.maps.suggestions import Targets
from osu_coach.domain.player import build_profile, comfort, replay_weight
from osu_coach.domain.replays import scope
from osu_coach.features.maps.playlists import stream_length_maps
from osu_coach.infra.library import analyze_files
from osu_coach.infra.map_pool import load_pool
from tests.conftest import replay_and_map
from tests.domain.player.helpers import (
    miss_causes,
    rate,
    records,
    stream_fall_behind,
    stream_limits,
    stream_speed_profile,
)


# ------------------------------------------------------------------ weights
def test_weight_is_one_inside_the_band_and_fades_outside():
    w = replay_weight([6.2, 6.6, 5.7, 7.2, 5.2, 8.2, 9.2, 3.2], 6.2)
    assert w[:3] == pytest.approx([1, 1, 1])
    assert w[3] == pytest.approx(math.exp(-0.5), rel=1e-6)  # 1★ above: 0.61
    assert w[4] == pytest.approx(w[3])  # symmetric
    assert w[5] < 0.02  # 2★ off: ~0.01
    assert w[6] < 1e-3 and w[7] < 1e-3  # 3★ off: no real effect
    assert (np.diff(replay_weight([6.7, 7.0, 7.5, 8.0], 6.2)) < 0).all()  # smooth decay


def test_unknown_stars_or_level_count_fully():
    assert replay_weight([np.nan, 5.0], 6.0)[0] == 1.0
    assert (replay_weight([3.0, 9.0], math.nan) == 1).all()


def _metas(rows, maps=None):
    return records(
        [
            {
                "key": f"r{i}",
                "stars": s,
                "date": d,
                "head_misses": m,
                "n_objects": 100,
                "completed": True,
                "beatmap_md5": md5,
            }
            for i, ((s, d, m), md5) in enumerate(zip(rows, maps or ["same"] * len(rows), strict=True))
        ]
    )


def test_level_comes_from_recent_replays():
    now = dt.datetime(2026, 10, 10, tzinfo=dt.UTC)
    old = [(7.5, now - dt.timedelta(days=400 + i), 0) for i in range(30)]  # years ago: 7.5★ clean
    new = [(6.0 + 0.01 * i, now - dt.timedelta(days=i), 1) for i in range(20)]  # this month: ~6★ clean
    lv = comfort(_metas(old + new))
    assert lv.recent_n == 20
    assert lv.stars == pytest.approx(6.14, abs=0.05)
    assert lv.status == "provisional" and lv.measured is None  # all on one map: no measured comfort level


def test_level_uses_the_newest_15_when_few_recent():
    now = dt.datetime(2026, 10, 10, tzinfo=dt.UTC)
    rows = [(5.0, now - dt.timedelta(days=100 * i), 0) for i in range(40)]
    assert comfort(_metas(rows)).recent_n == 15


def test_comfort_is_measured_from_three_different_clean_setups():
    now = dt.datetime(2026, 10, 10, tzinfo=dt.UTC)
    rows = [(stars, now - dt.timedelta(days=i), 0) for i, stars in enumerate([5.0, 5.0, 6.0, 7.0])]
    measured = comfort(_metas(rows, ["a", "a", "b", "c"]))
    assert measured.status == "measured" and measured.setups == 3
    assert measured.stars == pytest.approx(6.5)  # 75th percentile of the setups' medians 5, 6 and 7
    two = comfort(_metas(rows[:3], ["a", "a", "b"]))
    assert two.status == "provisional" and two.setups == 2 and two.measured is None
    assert two.stars == pytest.approx(5.5)  # 75th percentile of the clean plays
    missed = comfort(_metas([(4.0, now, 20), (5.0, now, 20)]))  # no clean play at all
    assert missed.status == "provisional" and missed.stars == pytest.approx(4.25 - 0.4)
    assert comfort([]).status == "none"


@pytest.fixture(scope="module")
def analyses():
    names = [
        "circlecore__legit__legit-12.osr",
        "osrparse__resources__replay.osr",
        "circlecore__low_frametime_old__replay-osu_24722_433541214.osr",
    ]
    return [analyze_files(*replay_and_map(n)[:2]) for n in names]


def test_level_override_drives_the_weights(analyses):
    stars = [a.meta.stars for a in analyses]
    target = stars[0]
    p = build_profile(analyses, level=target)
    assert p.levels.level_stars == target and p.levels.level_override
    assert np.array(p.weights) == pytest.approx(replay_weight(stars, target))
    assert p.weights[0] == 1.0
    # a replay far from the level hardly counts: weighted misses follow the replay weights
    far = build_profile(analyses, level=target + 20)
    assert far.overview.weighted_replays < 0.01
    assert sum(far.miss_breakdown.values()) < 0.01 * sum(far.miss_breakdown_raw.values())


# ------------------------------------------------------------------ miss causes
def test_aim_misses_on_fast_patterns_are_speed_aim():
    O = pd.DataFrame(
        {
            "head_hit": [False, False, False, False, False, True],
            "miss_reason": ["aim", "aim", "aim", "no_tap", "aim", None],
            "run_len": [12, 1, 1, 12, 3, 12],
            "pattern": ["stream", "jump", "jump", "stream", "burst", "stream"],
            "dt_real": [60.0, 300.0, 110.0, 60.0, 80.0, 60.0],
        }
    )
    got = [None if pd.isna(c) else c for c in miss_causes(O)]
    assert got == ["speed_aim", "aim", "speed_aim", "no_tap", "speed_aim", None]


def _streams(rows):
    out = []
    for bpm, n, miss_every, reason in rows:
        for i in range(n):
            miss = miss_every and i % miss_every == 0
            out.append(
                {
                    "run_len": 20,
                    "run_pos": 1 + i % 19,
                    "stream_bpm": bpm + 2,
                    "head_hit": not miss,
                    "miss_reason": reason if miss else None,
                    "err_real": 5.0,
                    "played": True,
                    "kind": "circle",
                    "head_result": 300,
                    "pattern": "stream",
                }
            )
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


# ------------------------------------------------------------------ stamina inside streams (precision)
def _long_streams(n_runs, length, err_fn, seed=3, bpm=200.0):
    rng = np.random.default_rng(seed)
    rows = []
    for run in range(n_runs):
        for pos in range(length):
            size = err_fn(pos) + abs(rng.normal(0, 1))
            rows.append(
                {
                    "run_len": length,
                    "run_pos": pos,
                    "run_id": run,
                    "replay_key": "r",
                    "head_hit": True,
                    "err_real": size * (1 if rng.random() < 0.5 else -1),  # early and late alike
                    "stream_bpm": bpm,
                    "played": True,
                    "kind": "circle",
                }
            )
    return pd.DataFrame(rows)


def test_stamina_onset_uses_absolute_error_not_the_average():
    """Early and late taps cancel in the plain average (≈ 0 ms); the absolute error shows the precision
    falling apart after note 21 (10 ms → 50 ms)."""
    O = _long_streams(80, 48, lambda pos: 10.0 if pos < 20 else 10.0 + 1.5 * (pos - 20))
    fb = stream_fall_behind(O)
    assert abs(fb["curve"]["err"].mean()) < 3  # the signed average says nothing
    assert fb["start_note"] == pytest.approx(21, abs=1)  # note numbers count from 1
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
        rows += [
            {
                "run_len": 20,
                "run_pos": 1 + i % 19,
                "stream_bpm": bpm + 2,
                "head_hit": True,
                "miss_reason": None,
                "err_real": float(x),
                "played": True,
                "kind": "circle",
                "head_result": 300,
                "pattern": "stream",
                "replay_key": f"{bpm}-{k}",
            }
            for i, x in enumerate(e)
        ]
    return rows


def test_stream_ur_is_measured_per_play():
    """Two 100 UR plays with averages 20 ms apart pool to ~140 UR; per play it stays 100."""
    prof = stream_speed_profile(pd.DataFrame(_plays_at(200, 100, [-10, 10]))).set_index("bpm_bin")
    assert prof.loc[200, "ur"] == pytest.approx(100, abs=1) and prof.loc[200, "ur_best"] == pytest.approx(100, abs=1)
    assert prof.loc[200, "ur_pooled"] == pytest.approx(141, abs=3) and prof.loc[200, "ur_plays"] == 2


def test_stream_ur_trend_rises_and_marks_weak_speeds():
    rows = []
    for i, bpm in enumerate(range(180, 270, 10)):
        ur = 100 + 2 * (bpm - 180) + (150 if bpm == 200 else 0)  # 200 BPM sticks out
        rows += _plays_at(bpm, ur, [0, 5, -5], seed=i)
    prof = stream_speed_profile(pd.DataFrame(rows)).set_index("bpm_bin")
    assert list(prof.index[prof["weak"]]) == [200]
    assert prof.loc[250, "ur_trend"] > prof.loc[180, "ur_trend"]  # rises with speed
    assert prof.loc[220, "ur_trend"] == pytest.approx(180, abs=8)  # not pulled up by the weak speed


def test_stream_length_maps_pick_streams_of_that_length():
    pool = load_pool()
    t = Targets(comfort=6.0, stream_bpm=220.0)
    maps = stream_length_maps(pool, t, 32, 48, n=5)
    assert 0 < len(maps) <= 5
    full = pool.set_index("md5").loc[maps["md5"]]
    assert full["max_run"].between(32, 48).all()
    assert maps["why"].str.contains("longest stream").all()


# ------------------------------------------------------------------ selection
UTC = dt.UTC


def _meta(md5, rate, score, acc, completed=True, key=None):
    return {
        "beatmap_md5": md5,
        "rate": rate,
        "score": score,
        "accuracy": acc,
        "completed": completed,
        "key": key or f"{md5}-{rate}-{score}",
    }


def test_best_replays_one_per_map_and_speed():
    plays = [
        _meta("a", 1.0, 500, 0.95),
        _meta("a", 1.0, 700, 0.90),
        _meta("a", 1.5, 300, 0.80),
        _meta("a", 1.0, 900, 0.99, completed=False),  # failed: never "best"
        _meta("b", 1.0, 400, 0.97),
        _meta("b", 1.0, 400, 0.98),
        _meta("c", 0.75, 0, 0.5, completed=False),
    ]
    best = scope.best_replays(plays)
    got = {(m["beatmap_md5"], m["rate"]): (m["score"], m["accuracy"]) for m in best}
    assert got == {("a", 1.0): (700, 0.90), ("a", 1.5): (300, 0.80), ("b", 1.0): (400, 0.98)}
    assert scope.select(plays, "all") == plays


def test_last_session_is_the_newest_run_of_close_plays():
    t = dt.datetime(2026, 10, 7, 20, 0, tzinfo=UTC)
    times = [
        t,
        t + dt.timedelta(minutes=40),
        t + dt.timedelta(minutes=70),  # one session
        t - dt.timedelta(hours=5),
        t - dt.timedelta(days=2),
    ]
    assert scope.last_session_start(times) == t
    since, until = scope.date_window("session", [x.isoformat() for x in times], now=times[0], tz=UTC)
    assert since == t and until is None


def test_date_windows():
    now = dt.datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    assert scope.date_window("all", now=now, tz=UTC) == (None, None)
    assert scope.date_window("7d", now=now, tz=UTC)[0] == now - dt.timedelta(days=7)
    assert scope.date_window("30d", now=now, tz=UTC)[0] == now - dt.timedelta(days=30)
    since, until = scope.date_window("custom", start=dt.date(2026, 10, 1), end=dt.date(2026, 10, 2), now=now, tz=UTC)
    assert since == dt.datetime(2026, 10, 1, tzinfo=UTC) and until == dt.datetime(2026, 10, 3, tzinfo=UTC)


def test_filter_refs_by_header_time():
    refs = [{"timestamp": "2026-10-09T21:00:00"}, {"timestamp": "2026-09-01T10:00:00"}, {"timestamp": ""}]
    since = dt.datetime(2026, 10, 1, tzinfo=UTC)
    assert scope.filter_refs(refs, since, None) == refs[:1]
    assert scope.filter_refs(refs, None, None) == refs
    assert scope.filter_refs(refs, None, since) == refs[1:2]


# ------------------------------------------------------------------ stamina: tempo you keep up, and for how long
def _map(key, segments, completed=True, start=1000.0):
    """A play from (notes, ms between notes, outcome) segments, in order; outcome = None (hit) or a miss reason."""
    rows, t = [], start
    for notes, gap, miss in segments:
        for _ in range(notes):
            t += gap
            rows.append(
                {
                    "time": t,
                    "head_hit": miss is None,
                    "miss_reason": miss,
                    "kind": "circle",
                    "completed": completed,
                    "replay_key": key,
                    "played": True,
                    "rate": 1.0,
                    "run_id": -1,
                    "run_len": 1,
                    "run_pos": 0,
                    "stream_bpm": np.nan,
                }
            )
    return rows


def _stream_for(seconds, bpm, miss=None):
    gap = 15000.0 / bpm
    return (int(seconds * 1000 / gap), gap, miss)


def test_tempo_curve_is_the_fastest_tempo_kept_up_for_each_duration():
    from tests.domain.player.helpers import tempo_curve

    C = tempo_curve(pd.DataFrame(_map("a", [_stream_for(150, 220)]))).set_index("window")
    assert C.loc[[10, 30, 60, 120], "bpm"].tolist() == pytest.approx([220] * 4, rel=0.01)
    assert 300 not in C.index  # the play is shorter than 5 minutes
    # a 20-second burst at 260 BPM inside slower tapping: fast for 10 s, not for a minute
    C = tempo_curve(
        pd.DataFrame(_map("b", [_stream_for(60, 150), _stream_for(20, 260), _stream_for(60, 150)]))
    ).set_index("window")
    assert C.loc[10, "bpm"] == pytest.approx(260, rel=0.01)
    assert C.loc[60, "bpm"] < 190


def test_undertapping_stops_the_tempo_but_sloppy_hits_and_overstreaming_count():
    from tests.domain.player.helpers import tempo_curve

    clean = tempo_curve(pd.DataFrame(_map("c", [_stream_for(130, 220)]))).set_index("window")["bpm"]
    # every 3rd note a 100 / an early miss where you tapped: your fingers kept going
    rows = _map("s", [_stream_for(130, 220)])
    for i, r in enumerate(rows):
        if i % 3 == 0:
            r["head_hit"], r["miss_reason"] = False, "early"
    sloppy = tempo_curve(pd.DataFrame(rows)).set_index("window")["bpm"]
    assert sloppy[120] == pytest.approx(clean[120])
    # after 40 s the fingers give in: half the notes get no tap
    rows = _map("u", [_stream_for(40, 220), _stream_for(90, 220)])
    for i, r in enumerate(rows):
        if r["time"] > 41000 and i % 2:
            r["head_hit"], r["miss_reason"] = False, "no_tap"
    tired = tempo_curve(pd.DataFrame(rows)).set_index("window")["bpm"]
    assert tired[30] == pytest.approx(clean[30], rel=0.02)  # the first 40 s were fine
    assert tired[120] < 0.5 * clean[120]  # but not for 2 minutes


def test_stamina_rating_against_the_typical_tempo_for_the_level():
    def maps(bpm):
        return sum((_map(f"m{k}", [_stream_for(100, bpm)]) for k in range(3)), [])

    # at 6★ the typical stream speed is 210 BPM: × 0.55 for 10 s (115.5), × 0.47 for 30 s, × 0.41 for 1 min
    base, fast = rate(maps(118))["stamina"], rate(maps(133))["stamina"]
    assert [p["duration"] for p in base.parts] == [10, 30, 60]  # the plays are shorter than 2 minutes
    assert [p["expected"] for p in base.parts] == pytest.approx([115.5, 98.7, 86.1])
    assert fast.score - base.score == pytest.approx(75 * math.log2(133 / 118), abs=0.5)  # 13% faster = +13
    # one map played three times counts once: not enough map/mod setups for a rating
    again = [dict(row, map_md5="same") for row in maps(133)]
    assert rate(again)["stamina"].score is None


def test_low_tempo_marathons_never_beat_controlled_death_streams():
    """A 45-minute marathon of 1/2 notes at 180 BPM, played clean, vs. 3-minute maps of 280 BPM streams."""
    marathon = sum((_map(f"mar{k}", [(16200, 166.7, None)]) for k in range(3)), [])
    death = sum((_map(f"d{k}", [_stream_for(25, 280), (12, 333.0, None)] * 7) for k in range(3)), [])
    m, d = rate(marathon, theta=8.0)["stamina"], rate(death, theta=8.0)["stamina"]
    five_minutes = next(p for p in m.parts if p["duration"] == 300)
    assert five_minutes["measured"] == pytest.approx(90, rel=0.02)  # 1/2 notes at 180 BPM = 90 as stream BPM
    assert d.score > m.score + 30


# ------------------------------------------------------------------ sliders: how hard the sliders are you hold
def _sliders(key, n, vel, length, turn=0.0, corners=0, bends=0, spans=1, broke=None, change=0.0, gap=1000.0):
    return [
        {
            "kind": "slider",
            "head_hit": True,
            "broke": bool(broke and i < broke),
            "replay_key": key,
            "radius": 32.0,
            "slider_vel_real": vel,
            "slider_len": length,
            "slider_spans": spans,
            "slider_turn": turn,
            "slider_corners": corners,
            "slider_bends": bends,
            "slider_vel_change": change,
            "slider_next_gap": gap,
            "played": True,
        }
        for i in range(n)
    ]


def test_slider_difficulty_grows_with_speed_length_and_shape():
    from tests.domain.player.helpers import slider_difficulty

    S = pd.DataFrame(
        _sliders("a", 1, 0.5, 60)
        + _sliders("b", 1, 0.5, 200)
        + _sliders("c", 1, 1.5, 200)
        + _sliders("d", 1, 1.5, 200, turn=2 * math.pi, corners=2, bends=2)
        + _sliders("e", 1, 1.5, 200, change=0.7)
        + _sliders("f", 1, 1.5, 200, gap=50)
    )
    d = slider_difficulty(S).tolist()
    assert 0 < d[0] < d[1]  # inside the follow circle: counts, but least
    assert d[1] < d[2] < d[3]  # longer < faster < curved with corners and bends
    assert d[4] > d[2] and d[5] > d[2]  # speed change and a quick next note add to it


def test_many_easy_sliders_dont_add_up_to_a_few_hard_ones():
    easy = rate(sum((_sliders(f"e{k}", 300, 0.4, 90) for k in range(5)), []))["sliders"]
    hard = rate(sum((_sliders(f"h{k}", 30, 0.7, 200, turn=math.pi, corners=1) for k in range(5)), []))["sliders"]
    assert hard.score > 50 and (easy.score is None or easy.score < 50)
    # breaking 3 of the 30 hardest sliders on every map costs about a quarter of the value
    broken = rate(sum((_sliders(f"b{k}", 30, 0.7, 200, turn=math.pi, corners=1, broke=3) for k in range(5)), []))
    assert broken["sliders"].measured == pytest.approx(hard.measured * 0.9**3)
    assert broken["sliders"].score < hard.score - 8


# ------------------------------------------------------------------ tapping speed
def _runs(key, bpm, n_runs, notes=8, miss=None, result=300):
    rows = []
    for r in range(n_runs):
        for pos in range(notes):
            bad = miss is not None and pos == 3
            rows.append(
                {
                    "replay_key": key,
                    "run_id": r,
                    "run_len": notes,
                    "run_pos": pos,
                    "stream_bpm": float(bpm),
                    "head_hit": not bad,
                    "miss_reason": miss if bad else None,
                    "head_result": 0 if bad else result,
                    "kind": "circle",
                    "played": True,
                }
            )
    return rows


def test_tapping_speed_is_the_bpm_you_tap_cleanly_and_ignores_cursor_misses():
    from tests.domain.player.helpers import speed_values

    clean = speed_values(pd.DataFrame(_runs("a", 240, 4))).iloc[0]
    assert clean["bpm"] == 240 and clean["clean"] == 4
    assert speed_values(pd.DataFrame(_runs("b", 240, 4, miss="aim"))).iloc[0]["bpm"] == 240  # cursor: fine
    assert np.isnan(speed_values(pd.DataFrame(_runs("c", 240, 4, miss="no_tap"))).iloc[0]["bpm"])  # fingers
    assert np.isnan(speed_values(pd.DataFrame(_runs("d", 240, 4, result=100))).iloc[0]["bpm"])  # mashing
    maps = lambda bpm: sum((_runs(f"m{k}", bpm, 3) for k in range(3)), [])  # noqa: E731
    # at 6★ the typical clean stream speed is 210 BPM; 75 points per doubling
    assert rate(maps(210))["speed"].score == pytest.approx(50)
    assert rate(maps(231))["speed"].score == pytest.approx(50 + 75 * math.log2(1.1), abs=0.05)


# ------------------------------------------------------------------ jump aim: distance x speed x combo
def _jumps(key, n, dist, dt, combo=1.0, completed=True, md5=None):
    return [
        {
            "replay_key": key,
            "pattern": "jump",
            "velocity_real": dist * 64.0 / dt,
            "radius": 32.0,
            "combo_ratio": combo,
            "completed": completed,
            "played": True,
            "map_md5": md5 or key,
            "rate": 1.0,
            "kind": "circle",
        }
        for _ in range(n)
    ]


def test_aim_is_distance_times_speed_times_combo():
    from tests.domain.player.helpers import aim_values

    V = aim_values(
        pd.DataFrame(
            _jumps("a", 40, 3.0, 200)
            + _jumps("b", 40, 3.0, 150)
            + _jumps("c", 40, 4.0, 200)
            + _jumps("d", 40, 4.0, 200, combo=0.5)
            + _jumps("e", 40, 9.0, 100, completed=False)
        )
    ).set_index("replay_key")
    assert V.loc["a", "intensity"] == pytest.approx(15.0)  # 3 circles in 0.2 s = 15 circles/s
    assert V.loc["b", "value"] > V.loc["a", "value"] and V.loc["c", "value"] > V.loc["a", "value"]
    assert V.loc["d", "value"] == pytest.approx(V.loc["c", "value"] * 0.5**0.8)  # half the combo
    assert "e" not in V.index  # failed plays don't count


def test_aim_rating_is_jump_speed_times_the_share_of_them_hit():
    clean = sum((_jumps(f"f{k}", 40, 3.5, 200) for k in range(3)), [])
    assert rate(clean)["aim"].score == pytest.approx(50)  # 17.5 circles/s, every jump hit = typical at 6★
    # half of the 30 fastest jumps missed: (1/2)^0.8 of the value
    half = [
        dict(row, head_hit=i % 40 >= 15)
        for i, row in enumerate(sum((_jumps(f"g{k}", 40, 3.5, 200) for k in range(3)), []))
    ]
    assert rate(half)["aim"].score == pytest.approx(50 - 25 * 0.8)


# ------------------------------------------------------------------ reading: low AR, accuracy, BPM changes
def _read_play(key, ar, acc, stars=6.0, bpm_changes=0, hit_after=True, hidden=False, n=200, gap=200.0):
    rows = []
    for i in range(n):
        seg = i * (bpm_changes + 1) // n  # bpm_changes evenly spread changes
        bpm = 180.0 if seg % 2 == 0 else 240.0
        first = i > 0 and (i * (bpm_changes + 1) // n) != ((i - 1) * (bpm_changes + 1) // n)
        rows.append(
            {
                "replay_key": key,
                "map_md5": key,
                "rate": 1.0,
                "time": i * gap,
                "kind": "circle",
                "map_ar": ar,
                "accuracy": acc,
                "stars": stars,
                "hidden": hidden,
                "flashlight": False,
                "completed": True,
                "played": True,
                "bpm_real": bpm,
                "head_hit": True,
                "head_result": 300 if (hit_after or not first) else 100,
            }
        )
    return rows


def test_reading_counts_low_ar_accuracy_and_bpm_changes():
    from osu_coach.domain.player import usual_ar
    from tests.domain.player.helpers import reading_values

    assert float(usual_ar(6.0)) == 9.5
    V = reading_values(
        pd.DataFrame(
            _read_play("usual", 9.5, 0.95)
            + _read_play("low", 6.5, 0.95)
            + _read_play("low_hd", 6.5, 0.95, hidden=True)
            + _read_play("sloppy", 6.5, 0.85)
            + _read_play("bpm", 9.5, 0.95, bpm_changes=8)
            + _read_play("bpm_missed", 9.5, 0.95, bpm_changes=8, hit_after=False)
        )
    ).set_index("replay_key")
    assert V.loc["usual", "value"] == pytest.approx(0.95**8)
    assert V.loc["usual", "nps"] == pytest.approx(5.0, rel=0.01)  # a note every 200 ms
    assert V.loc["low", "ar_factor"] == pytest.approx(2.0, rel=0.01)  # 3 AR lower than usual = twice the demand
    assert V.loc["low_hd", "value"] == pytest.approx(V.loc["low", "value"] * 1.2)
    assert V.loc["sloppy", "value"] < V.loc["low", "value"] / 2  # 85% accuracy: low AR alone isn't enough
    assert V.loc["bpm", "bpm_changes"] == 8 and V.loc["bpm", "bpm_factor"] == pytest.approx(1.5)
    assert V.loc["bpm_missed", "bpm_factor"] == pytest.approx(1 + 0.5 * 0.75)  # 1 of 4 notes after each change a 100
    maps = lambda ar: sum((_read_play(f"{ar}-{k}", ar, 0.95) for k in range(3)), [])  # noqa: E731
    # 50 = the usual AR for the map at 95%; 3 AR lower on a busy map = twice the demand = +25
    assert rate(maps(9.5))["reading"].score == pytest.approx(50)
    assert rate(maps(6.5))["reading"].score == pytest.approx(75, abs=0.5)


def test_low_ar_on_a_slow_map_counts_less_than_on_a_busy_one():
    from tests.domain.player.helpers import reading_values

    V = reading_values(
        pd.DataFrame(
            _read_play("slow", 3.5, 0.95, gap=333.3)  # 3 circles per second
            + _read_play("busy", 3.5, 0.95, gap=153.8)  # 6.5 per second
            + _read_play("busy_usual", 9.5, 0.95, gap=153.8)
        )
    ).set_index("replay_key")
    assert V.loc["slow", "ar_factor"] == pytest.approx(2 ** (2 * 0.6), rel=0.01)  # 6 AR lower, but slow
    assert V.loc["busy", "ar_factor"] == pytest.approx(2 ** (2 * 1.3), rel=0.01)
    assert V.loc["busy_usual", "ar_factor"] == pytest.approx(1.0)  # busy at the usual AR: no reading bonus


def test_high_ar_counts_as_reading_too():
    from tests.domain.player.helpers import reading_values

    V = reading_values(pd.DataFrame(_read_play("usual", 9.5, 0.95) + _read_play("high", 11.0, 0.95))).set_index(
        "replay_key"
    )
    assert V.loc["high", "ar_factor"] == pytest.approx(2.0, rel=0.02)  # 1.5 AR above usual = twice the demand
    assert V.loc["usual", "ar_factor"] == pytest.approx(1.0)


def test_stamina_in_long_streams_by_speed_is_relative_to_the_note_gap():
    from tests.domain.player.helpers import stream_fall_behind

    fast = _long_streams(40, 32, lambda pos: 15.0, seed=8, bpm=250.0)
    slow = _long_streams(40, 32, lambda pos: 15.0, seed=9, bpm=200.0)
    slow["replay_key"] = "s"
    fb = stream_fall_behind(pd.concat([fast, slow], ignore_index=True))
    c = fb["curves_bpm"].groupby("group")["rel_err"].mean()
    # the same ms error is a bigger share of the gap at 250 BPM (60 ms between notes) than at 200 (75 ms)
    assert c["240–269 BPM"] > c["180–209 BPM"] * 1.2
