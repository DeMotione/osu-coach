import math

import numpy as np
import pandas as pd
import pytest

from osu_coach.analysis import analyze_files
from osu_coach.profile import (aim_regression, build_profile, fit_miss_model, quadrant_stats, stream_speed_profile,
                               worst_quadrant)
from tests.conftest import replay_and_map


def synthetic_objects(n=4000, seed=1, weak_quadrant="bottom-right", base_miss=0.04, weak_miss=0.12):
    rng = np.random.default_rng(seed)
    x = rng.uniform(0, 512, n)
    y = rng.uniform(0, 384, n)
    quad = np.where(y < 192, "top", "bottom").astype(object) + "-" + np.where(x < 256, "left", "right").astype(object)
    p = np.where(quad == weak_quadrant, weak_miss, base_miss)
    miss = rng.uniform(size=n) < p
    return pd.DataFrame({"x": x, "y": y, "quadrant": quad, "grid": 0, "head_hit": ~miss, "played": True,
                         "kind": "circle", "miss_reason": np.where(miss, "aim", None), "along": 0.0,
                         "err_dx": 0.0, "err_dy": 0.0})


def test_worst_quadrant_is_found_and_significant():
    q = quadrant_stats(synthetic_objects())
    assert set(q.index) == {"top-left", "top-right", "bottom-left", "bottom-right"}
    w = worst_quadrant(q)
    assert w["quadrant"] == "bottom-right"
    assert w["relative_risk"] > 2
    assert w["significant"]


def test_no_worst_quadrant_when_uniform():
    q = quadrant_stats(synthetic_objects(weak_miss=0.04, seed=3))
    w = worst_quadrant(q)
    assert w is None or not w["significant"]


def _movements(scale=(1.0, 1.0), rot_deg=0.0, offset=(0.0, 0.0), n=600, seed=2):
    rng = np.random.default_rng(seed)
    sx, sy = rng.uniform(80, 430, n), rng.uniform(60, 320, n)
    ang = rng.uniform(0, 2 * math.pi, n)
    d = rng.uniform(120, 260, n)
    ox, oy = np.clip(sx + d * np.cos(ang), 0, 512), np.clip(sy + d * np.sin(ang), 0, 384)
    ix, iy = ox - sx, oy - sy
    th = math.radians(rot_deg)
    ax = scale[0] * (math.cos(th) * ix - math.sin(th) * iy)
    ay = scale[1] * (math.sin(th) * ix + math.cos(th) * iy)
    cx, cy = sx + ax + offset[0] + rng.normal(0, 3, n), sy + ay + offset[1] + rng.normal(0, 3, n)
    return pd.DataFrame({"start_x": sx, "start_y": sy, "x": ox, "y": oy, "err_dx": cx - ox, "err_dy": cy - oy,
                         "dist_norm": d / 73.0, "radius": 36.5, "played": True, "kind": "circle",
                         "head_hit": True, "miss_reason": None})


def test_regression_recovers_overshoot_scale():
    r = aim_regression(_movements(scale=(1.10, 1.10)))
    assert r["scale_x"] == pytest.approx(1.10, abs=0.02)
    assert r["scale_y"] == pytest.approx(1.10, abs=0.02)
    assert abs(r["rotation_deg"]) < 1


def test_regression_recovers_clockwise_rotation():
    r = aim_regression(_movements(rot_deg=6))
    assert r["rotation_deg"] == pytest.approx(6, abs=1)


def test_regression_recovers_constant_offset():
    r = aim_regression(_movements(offset=(-6, 4)))
    assert r["offset_x"] == pytest.approx(-6, abs=1)
    assert r["offset_y"] == pytest.approx(4, abs=1)


def test_stream_profile_bins_by_bpm():
    rows = []
    for bpm, miss in ((150, 0.01), (170, 0.03), (190, 0.15)):
        for i in range(300):
            rows.append({"run_len": 12, "run_pos": i % 12, "stream_bpm": bpm + 2, "head_hit": (i % 100) >= miss * 100,
                         "err_real": 5.0, "played": True, "kind": "circle", "head_result": 300, "pattern": "stream"})
    prof = stream_speed_profile(pd.DataFrame(rows))
    assert list(prof["bpm_bin"]) == [150, 170, 190]
    assert prof.loc[prof["bpm_bin"] == 190, "miss_rate"].iloc[0] == pytest.approx(0.15, abs=0.01)


def test_miss_model_increases_with_difficulty():
    rng = np.random.default_rng(0)
    eq = rng.uniform(1, 5, 5000)
    p = 1 / (1 + np.exp(-(eq - 4) * 2))
    df = pd.DataFrame({"local_eq": eq, "head_hit": rng.uniform(size=5000) >= p})
    model = fit_miss_model(df)
    assert model(np.array([2.0]))[0] < model(np.array([4.5]))[0]


@pytest.fixture(scope="module")
def real_profile():
    names = ["circlecore__legit__legit-12.osr", "osrparse__resources__replay.osr",
             "circlecore__low_frametime_old__replay-osu_24722_433541214.osr"]
    analyses = [analyze_files(*replay_and_map(n)[:2]) for n in names]
    return build_profile(analyses)


def test_profile_overview(real_profile):
    ov = real_profile.overview
    assert ov["replays"] == 3
    assert ov["objects"] > 5000
    assert 0 <= ov["miss_rate"] < 0.2


def test_profile_skill_scores_in_range(real_profile):
    for name, s in real_profile.skills.items():
        if s["score"] is not None:
            assert 0 <= s["score"] <= 100, name
    assert {"aim", "speed", "accuracy"} <= set(real_profile.skills)


def test_profile_miss_breakdown_sums(real_profile):
    mb = real_profile.miss_breakdown
    assert sum(mb.values()) == real_profile.overview["head_misses"]
