"""Readiness for harder maps (skill levels in stars) and consistency per star band."""

import math

import numpy as np
import pandas as pd
import pytest

from osu_coach.profile.domain.readiness import (
    band_consistency,
    consistency_bands,
    curve_level,
    pool_levels,
    readiness,
)


def test_readiness_follows_the_square_of_the_star_ratio():
    assert readiness(7.0, 7.0) == 1
    assert readiness(5.0, 6.0) == pytest.approx(2 - 1.2**2)  # +1★ for a 5★ player feels 44% harder
    assert readiness(5.0, 5.5) == pytest.approx(2 - 1.1**2)
    assert readiness(7.0, 7.0 * math.sqrt(2)) == pytest.approx(0, abs=1e-12)  # twice the strain: out of reach
    assert readiness(7.0, 10.0) == 0
    assert readiness(8.0, 7.0) == 1  # easier maps never go above 100%
    assert readiness(None, 8.0) is None


@pytest.mark.parametrize(
    "combo,accuracy,score",
    [(0.95, 0.95, 95), (0.40, 0.90, 75), (0.90, 0.30, 72), (0.30, 0.20, 27)],
)
def test_either_combo_or_accuracy_carries_consistency(combo, accuracy, score):
    assert band_consistency(combo, accuracy) == pytest.approx(score, abs=0.5)


def _plays(n, stars, combo=1.0, accuracy=0.99, misses=0):
    return pd.DataFrame(
        {
            "key": [f"{stars}-{i}" for i in range(n)],
            "stars": stars,
            "max_combo": np.asarray(combo, dtype=float) * 1000,
            "map_max_combo": 1000,
            "accuracy": accuracy,
            "nmiss": misses,
        }
    )


def test_consistency_needs_ten_plays_in_a_band():
    bands = consistency_bands(pd.concat([_plays(10, 6.2), _plays(9, 6.7)]))
    assert [(b["low"], b["high"], b["plays"]) for b in bands] == [(6.0, 6.5, 10), (6.5, 7.0, 9)]
    assert bands[0]["score"] == pytest.approx(100) and bands[0]["full_combo_share"] == 1
    assert bands[1]["score"] is None and bands[1]["combo"] is None


def test_swings_between_plays_lower_consistency():
    steady = consistency_bands(_plays(12, 6.2, combo=0.9, accuracy=0.97))[0]
    chokes = consistency_bands(_plays(12, 6.2, combo=[1.0, 0.3] * 6, accuracy=0.97))[0]
    assert steady["combo"] == pytest.approx(0.9)
    assert chokes["combo"] < 0.4 < steady["combo"]
    assert chokes["score"] < steady["score"]


def test_curve_level_reads_a_power_law_back():
    stars = np.arange(5.0, 11.01, 0.25)
    rising = (stars, 2 * stars**1.5, np.full(len(stars), 100))
    falling = (stars, 200 * stars**-1.0, np.full(len(stars), 100))
    assert curve_level(2 * 8.0**1.5, rising) == pytest.approx(8.0)
    assert curve_level(200 / 6.5, falling) == pytest.approx(6.5)
    assert curve_level(10.0, (stars, np.full(len(stars), 10.0), np.full(len(stars), 100))) is None  # flat
    assert curve_level(None, rising) is None


def test_sliders_stay_within_half_a_star_of_the_hardest_pass():
    stars = np.arange(5.0, 11.01, 0.25)
    curves = {"slider_speed": (stars, stars, np.full(len(stars), 100))}
    levels = pool_levels({"slider_speed": 9.0, "hardest_pass": 7.0}, curves)
    assert levels["sliders"]["level"] == pytest.approx(7.5)
    assert levels["sliders"]["uncapped"] == pytest.approx(9.0) and levels["sliders"]["capped"]
    assert pool_levels({"slider_speed": 7.2, "hardest_pass": 7.0}, curves)["sliders"]["capped"] is False


def test_pool_levels_stay_near_the_hardest_pass():
    stars = np.arange(1.5, 13.01, 0.25)
    curves = {
        "reading": (stars, stars, np.full(len(stars), 100)),
        "slider_speed": (stars, stars, np.full(len(stars), 100)),
    }
    levels = pool_levels({"reading": 2.0, "slider_speed": 6.5, "hardest_pass": 7.0}, curves)
    assert (
        levels["reading"]["level"] == pytest.approx(5.0) and levels["reading"]["raised"]
    )  # a flat curve can't sink it
    assert levels["sliders"]["level"] == pytest.approx(6.5) and not levels["sliders"]["capped"]
