"""Consistency: combo and accuracy held from map to map on the maps up to a star below a star rating."""

import numpy as np
import pandas as pd
import pytest

from osu_coach.profile.domain.consistency import STAR_MIN_MAPS, combo_scale, map_score, star_consistency


@pytest.mark.parametrize(
    "combo,accuracy,score",
    [
        (0.30, 0.93, 73),  # 300 of 1000 combo at 93%: good, just not perfect
        (1.00, 0.90, 80),  # a full combo carries a lower accuracy
        (0.60, 0.92, 74),
        (0.15, 0.93, 37),  # hardly any combo held: fading
        (0.10, 0.99, 0),  # can't even keep 10% of the combo: bad, whatever the accuracy
        (1.00, 0.94, 100),
    ],
)
def test_holding_combo_counts_not_only_full_combos(combo, accuracy, score):
    assert 100 * float(map_score(combo, accuracy)) == pytest.approx(score, abs=0.5)


def test_combo_scale():
    assert [round(float(combo_scale(c)), 2) for c in (0.05, 0.1, 0.2, 0.3, 0.5, 1.0)] == [0, 0, 0.3, 0.48, 0.7, 1]


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


def test_eight_different_maps_up_to_a_star_below():
    c = star_consistency(_plays(STAR_MIN_MAPS, 6.0), 6.2, comfort=True)
    assert (c["low"], c["high"], c["maps"]) == (pytest.approx(5.2), 6.2, 8)
    assert c["score"] == pytest.approx(100) and c["full_combo_share"] == 1 and c["needs"] is None


def test_harder_maps_dont_count_until_you_get_there():
    """At a 6.2★ comfort level a 6.5★ map doesn't count (it does at 6.7★); nor does one more than a star easier."""
    plays = pd.concat([_plays(5, 6.0), _plays(6, 6.5, start=5), _plays(3, 5.1, start=11)])
    c = star_consistency(plays, 6.2, comfort=True)
    assert c["score"] is None and c["reason"] == "Not enough data" and c["maps"] == 5
    assert c["needs"].startswith("Play 3 more different maps between 5.2★ and 6.2★")
    assert "your 6.2★ comfort level" in c["needs"] and "Harder maps don't count" in c["needs"]
    at = star_consistency(plays, 6.7)  # 5.7–6.7★: the 6★ and the 6.5★ maps, enough for a score there
    assert at["maps"] == 11 and at["score"] is not None
    assert "consistency at 7.1★" in star_consistency(plays, 7.1)["needs"]  # 6.1–7.1★: only the 6 maps of 6.5★


def test_harder_maps_within_the_span_count_more():
    """At 6.7★ a 6.7★ map counts twice as much as a 5.7★ one: playing well only on easy maps doesn't carry it."""
    easy_good = pd.concat([_plays(8, 5.7, combo=1.0, accuracy=0.94), _plays(8, 6.7, combo=0.3, accuracy=0.9, start=8)])
    hard_good = pd.concat([_plays(8, 5.7, combo=0.3, accuracy=0.9), _plays(8, 6.7, combo=1.0, accuracy=0.94, start=8)])
    assert star_consistency(easy_good, 6.7)["map_score"] < star_consistency(hard_good, 6.7)["map_score"]


def test_retrying_one_map_adds_no_map():
    c = star_consistency(_plays(20, 5.0, maps=3), 5.0)
    assert c["plays"] == 20 and c["maps"] == 3 and c["score"] is None
    assert "Play 5 more different maps" in c["needs"]


def test_no_comfort_level_yet():
    c = star_consistency(_plays(10, 5.0), None)
    assert c["score"] is None and c["needs"].startswith("First your comfort level")


def test_swings_between_maps_lower_consistency():
    steady = star_consistency(_plays(12, 5.0, combo=0.6, accuracy=0.92), 5.0)
    swings = star_consistency(_plays(12, 5.0, combo=[1.0, 0.25] * 6, accuracy=0.92), 5.0)
    assert steady["swing"] == pytest.approx(0) and steady["score"] == pytest.approx(74, abs=0.5)
    assert swings["mean_combo"] > steady["mean_combo"]  # more combo on average ...
    assert swings["score"] < steady["score"]  # ... but it swings from a full combo to a quarter of it
