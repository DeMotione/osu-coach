"""Consistency per star band: combo and accuracy held across plays of the same star rating."""

import numpy as np
import pandas as pd
import pytest

from osu_coach.profile.domain.consistency import band_consistency, consistency_bands


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
