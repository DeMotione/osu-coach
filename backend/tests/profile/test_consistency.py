"""Consistency: combo and accuracy held from map to map on different maps around the comfort level."""

import numpy as np
import pandas as pd
import pytest

from osu_coach.profile.domain.consistency import COMFORT_MIN_MAPS, comfort_consistency, held_score


@pytest.mark.parametrize(
    "combo,accuracy,score",
    [(0.95, 0.95, 95), (0.40, 0.90, 75), (0.90, 0.30, 72), (0.30, 0.20, 27)],
)
def test_either_combo_or_accuracy_carries_consistency(combo, accuracy, score):
    assert held_score(combo, accuracy) == pytest.approx(score, abs=0.5)


def _plays(n, stars, combo=1.0, accuracy=0.99, misses=0, maps=None, start=0):
    """``n`` plays, each on a map of its own unless ``maps`` names how many different maps they are spread over."""
    return pd.DataFrame(
        {
            "key": [f"{stars}-{start + i}" for i in range(n)],
            "beatmap_md5": [f"map{(start + i) % maps if maps else start + i}" for i in range(n)],
            "stars": stars,
            "max_combo": np.asarray(combo, dtype=float) * 1000,
            "map_max_combo": 1000,
            "accuracy": accuracy,
            "nmiss": misses,
        }
    )


def test_eight_different_maps_within_a_star_of_comfort():
    c = comfort_consistency(_plays(COMFORT_MIN_MAPS, 5.6), 5.0)
    assert (c["low"], c["high"], c["maps"]) == (4.0, 6.0, 8)
    assert c["score"] == pytest.approx(100) and c["full_combo_share"] == 1 and c["needs"] is None


def test_until_then_it_says_what_to_play():
    plays = pd.concat([_plays(5, 4.5), _plays(4, 7.0, start=5)])  # 7★ is more than a star above comfort
    c = comfort_consistency(plays, 5.0)
    assert c["score"] is None and c["reason"] == "Not enough data" and c["maps"] == 5
    assert c["needs"].startswith("Play 3 more different maps between 4.0★ and 6.0★")


def test_retrying_one_map_adds_no_map():
    c = comfort_consistency(_plays(20, 5.0, maps=3), 5.0)
    assert c["plays"] == 20 and c["maps"] == 3 and c["score"] is None
    assert "Play 5 more different maps" in c["needs"]


def test_no_comfort_level_yet():
    c = comfort_consistency(_plays(10, 5.0), None)
    assert c["score"] is None and c["needs"].startswith("First your comfort level")


def test_swings_between_maps_lower_consistency():
    steady = comfort_consistency(_plays(12, 5.0, combo=0.9, accuracy=0.97), 5.0)
    chokes = comfort_consistency(_plays(12, 5.0, combo=[1.0, 0.3] * 6, accuracy=0.97), 5.0)
    assert steady["combo"] == pytest.approx(0.9)
    assert chokes["combo"] < 0.4 < steady["combo"]
    assert chokes["score"] < steady["score"]
