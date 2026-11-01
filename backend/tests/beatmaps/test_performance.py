import math

import pytest
import rosu_pp_py as rosu

from osu_coach.beatmaps.performance import calculate
from tests.conftest import sample_paths


@pytest.mark.parametrize("client", ["stable", "lazer"])
@pytest.mark.parametrize("mods", [0, 8, 16, 24, 64, 72, 80, 88])
def test_pp_matches_explicit_rosu_fc_scenario(client, mods):
    _, path = sample_paths("mot1one__lazer_nm.osr")
    data = path.read_bytes()
    expected = (
        rosu.Performance(
            mods=mods, lazer=client == "lazer", accuracy=98, hitresult_priority=rosu.HitResultPriority.WorstCase
        )
        .calculate(rosu.Beatmap(bytes=data))
        .pp
    )
    assert calculate(data, mods, client, 0.98) == pytest.approx(expected)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"accuracy": math.nan},
        {"accuracy": -0.1},
        {"accuracy": 100},
        {"misses": -1},
        {"misses": True},
        {"accuracy": True},
        {"mods": False},
        {"accuracy": 1.0, "misses": 1},
        {"combo": -1},
        {"mods": 128},
        {"client": "taiko"},
        {"client": "lazer", "misses": 1},
    ],
)
def test_invalid_or_unknown_outcomes_are_explicit(kwargs):
    _, path = sample_paths("mot1one__lazer_nm.osr")
    with pytest.raises(ValueError):
        calculate(path.read_bytes(), **kwargs)
