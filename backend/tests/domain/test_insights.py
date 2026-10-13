"""Chart aggregations of a profile (insights.py) on real replays and on hand-made data."""
import math

import numpy as np
import pandas as pd
import pytest

from osu_coach.domain import insights
from osu_coach.domain.analysis import analyze_files
from osu_coach.domain.profile import build_profile, click_points
from tests.conftest import replay_and_map

NAMES = ["circlecore__legit__legit-12.osr", "osrparse__resources__replay.osr", "mot1one__lazer_nm.osr",
         "mot1one__lazer_dthd_spinner.osr"]


@pytest.fixture(scope="module")
def analyses():
    return [analyze_files(*replay_and_map(n)[:2]) for n in NAMES]


@pytest.fixture(scope="module")
def prof(analyses):
    return build_profile(analyses)


def test_playfield_grid_is_8_by_6_and_leaves_thin_cells_empty(prof):
    g = insights.playfield_grid(prof)
    assert len(g["x"]) == 8 and len(g["y"]) == 6
    assert len(g["rate"]) == 6 and all(len(row) == 8 for row in g["rate"])
    rate, notes = np.array(g["rate"], float), np.array(g["notes"], float)
    assert np.isnan(rate[notes < insights.GRID_MIN_NOTES]).all()
    filled = rate[notes >= insights.GRID_MIN_NOTES]
    assert len(filled) and ((filled >= 0) & (filled <= 100)).all()
    assert notes.sum() == pytest.approx(insights.weights(insights.played(prof)).sum(), rel=1e-6)


def test_timing_histogram_shares_and_bins(prof):
    h = insights.timing_histogram(prof)
    assert len(h["centers"]) == 2 * insights.TIMING_RANGE_MS // insights.TIMING_BIN_MS
    assert all(len(h["counts"][r]) == len(h["centers"]) for r in (300, 100, 50))
    assert sum(h["shares"].values()) == pytest.approx(1.0)
    assert h["shares"][300] > h["shares"][100] > h["shares"][50]
    assert sum(sum(c) for c in h["counts"].values()) == pytest.approx(h["total"], rel=1e-6)
    assert -20 < h["mean"] < 20


def test_click_sample_keeps_the_real_miss_share():
    rng = np.random.default_rng(1)
    n = 20000
    C = pd.DataFrame({"x": rng.normal(0, 0.5, n), "y": rng.normal(0, 0.5, n), "radius": 36.0,
                      "hit": rng.random(n) > 0.1, "w": 1.0})
    drawn = insights.click_sample(C, n=4000)
    assert len(drawn) <= 4000
    assert (drawn["x"].abs() < insights.CLICK_RANGE).all() and (drawn["y"].abs() < insights.CLICK_RANGE).all()
    assert (~drawn["hit"]).mean() == pytest.approx((~C["hit"]).mean(), abs=0.02)
    # the same seed gives the same picture (the page doesn't flicker between requests)
    assert drawn.index.equals(insights.click_sample(C, n=4000).index)


def test_click_sample_draws_plays_far_from_the_level_less_often():
    n = 10000
    C = pd.DataFrame({"x": 0.0, "y": 0.0, "radius": 36.0, "hit": True, "w": np.r_[np.ones(n), np.full(n, 0.05)]})
    drawn = insights.click_sample(C, n=2000)
    assert (drawn.index < n).mean() > 0.8


def test_click_sample_on_real_clicks(prof):
    C = click_points(prof.objects, "screen")
    drawn = insights.click_sample(C)
    assert 0 < len(drawn) <= insights.CLICKS_DRAWN


def test_stream_time_series_offers_bands_with_enough_notes(prof):
    st = insights.stream_time_series(prof)
    assert st is not None and st["band_width"] == insights.STREAM_BAND
    S = insights.stream_notes(prof)
    counts = S["band"].value_counts()
    assert st["bands"] == sorted(int(b) for b in counts.index if counts[b] >= insights.STREAM_BAND_MIN)
    for along in ("map", "session"):
        lines = st["series"][along]["lines"]
        assert set(lines) == {"overall"} | {str(b) for b in st["bands"]}
        overall = lines["overall"]
        assert (overall["n"] >= insights.STREAM_BIN_MIN).all()
        assert ((overall["miss_rate"] >= 0) & (overall["miss_rate"] <= 100)).all()


def test_stream_bins_take_each_plays_own_average_out_of_the_ur():
    # two plays with the same spread but opposite average timing: pooled together they'd look sloppy
    rows = []
    for key, bias in (("a", -20.0), ("b", 20.0)):
        err = np.tile([-5.0, 5.0], 50) + bias
        rows += [{"replay_key": key, "map_min": 0.1, "err_real": e, "head_hit": True, "w": 1.0} for e in err]
    B = insights.stream_bins(pd.DataFrame(rows), "map_min", 0.5)
    assert len(B) == 1 and B["ur"].iloc[0] == pytest.approx(50.0) and B["miss_rate"].iloc[0] == 0


def test_stream_time_series_needs_streams():
    empty = build_profile([analyze_files(*replay_and_map("circlecore__legit__legit_snaps-22.osr")[:2])])
    st = insights.stream_time_series(empty)
    assert st is None or st["notes"] >= insights.STREAM_MIN_NOTES


def test_fall_behind_by_speed_finds_where_stamina_gives_in():
    cb = pd.DataFrame({"group": ["180–209 BPM"] * 3 + ["210–239 BPM"] * 3, "pos": [1, 5, 9] * 2,
                       "rel_err": [10, 11, 12, 10, 20, 30]})
    r = insights.fall_behind_by_speed(cb)
    assert r["worst"] == "210–239 BPM"
    assert {g["group"]: g["rise"] for g in r["groups"]} == {"180–209 BPM": 2, "210–239 BPM": 20}
    flat = cb.assign(rel_err=10)
    assert insights.fall_behind_by_speed(flat)["worst"] is None          # nothing rises more than 3 points
    assert insights.fall_behind_by_speed(None) == {"groups": [], "worst": None}


def test_slider_rates_by_length_and_speed(prof):
    r = insights.slider_rates(prof)
    assert r is not None and set(r) == {"length", "speed"}
    for part in r.values():
        rows = part["rows"]
        assert (rows["n"] >= insights.SLIDER_BIN_MIN).all()
        assert part["worst"] in set(rows["bin"])
        assert ((rows["head"] + rows["broke"]) <= 100 + 1e-9).all()


def test_hits_by_ar_rows_add_up(prof):
    R = insights.hits_by_ar(prof)
    assert len(R) and (R["n"] >= insights.AR_BIN_MIN).all()
    assert np.allclose(R[["300", "100", "50", "miss"]].sum(axis=1), 100)
    assert list(R["ar"]) == sorted(R["ar"]) and all(ar * 2 == int(ar * 2) for ar in R["ar"])


def test_key_hold_is_in_real_time(prof):
    assert 20 < insights.key_hold_ms(prof) < 300


def test_play_timing(analyses):
    t = insights.play_timing(analyses[0])
    n = len(t["time"])
    assert n > 100 and len(t["error"]) == len(t["result"]) == len(t["trend"]) == n
    assert set(t["result"]) <= {300, 100, 50}
    od = analyses[0].meta["od"]
    assert t["window_300"] == pytest.approx(80 - 6 * od)
    assert t["top"] > 0 and t["length_ms"] >= max(t["time"])
    assert not math.isnan(np.nanmean(t["trend"]))
