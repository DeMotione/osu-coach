"""Experimental skillset recommendation: the score F(m) of the suggested maps."""

import pytest

from osu_coach.domain.maps.skillset import recommend
from osu_coach.infra.map_pool import POOL_PATH, load_pool

pytestmark = pytest.mark.skipif(not POOL_PATH.exists(), reason="bundled pool not built")


OFFSETS = {"Warm-up": -15, "Comfort": -5, "Push": 5}


@pytest.mark.parametrize("theta", [2.5, 4.39, 6.5])
@pytest.mark.parametrize("ability", [0.0, 100.0])
def test_requested_demand_is_not_clamped_and_empty_stages_are_explicit(theta, ability):
    """The requested target stays literal even when the available map demands cannot reach it."""
    result = recommend(load_pool().to_dict("records"), theta, {"accuracy": ability}, "accuracy", ("accuracy",))
    for goal, stage in result.goals.items():
        assert stage.target_demand == ability + OFFSETS[goal]
        assert stage.star_max - stage.star_min == pytest.approx(0.4)
        if stage.maps:
            b = stage.maps[0].breakdown
            assert b.reachable_demand == b.target_demand == stage.target_demand
            assert stage.maps[0].formula_score <= 0
        else:
            assert stage.eligible == 0 and stage.excluded


def test_a_reachable_target_is_used_as_it_is():
    stage = recommend(load_pool().to_dict("records"), 4.39, {"accuracy": 50.0}, "accuracy", ("accuracy",)).goals[
        "Comfort"
    ]
    assert all(m.breakdown.reachable_demand == m.breakdown.target_demand == 45 for m in stage.maps)


def test_weak_other_skills_count_overload_above_player_margin():
    abilities = {"accuracy": 0.0, "aim": 10.0, "speed": 20.0}
    for skill in abilities:
        result = recommend(load_pool().to_dict("records"), 4.39, abilities, skill, tuple(abilities))
        for stage in result.goals.values():
            for best in stage.maps[:1]:
                for part in best.breakdown.bottlenecks:
                    floor = part.ability + part.margin
                    assert part.overload == pytest.approx(max(0.0, part.demand - floor))


def test_sparse_timing_stage_does_not_widen_star_window():
    warmup = recommend(load_pool().to_dict("records"), 2.5, {"accuracy": 0.0}, "accuracy", ("accuracy",)).goals[
        "Warm-up"
    ]
    assert warmup.maps == ()
    assert warmup.star_max - warmup.star_min == pytest.approx(0.4)
    assert warmup.excluded["Outside star window"] > 0
