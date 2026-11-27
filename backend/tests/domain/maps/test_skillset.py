"""Experimental skillset recommendation: the score F(m) of the suggested maps."""

import pytest

from osu_coach.domain.maps.focus import parse_focus
from osu_coach.domain.maps.skillset import (
    OVER,
    _features,
    in_ar_range,
    rated_skills,
    recommend,
    recommend_modified,
    star_targets,
    typical_ar,
)
from osu_coach.domain.maps.suggestions import SKILLS
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


def test_composites_of_chosen_skills_are_those_of_all():
    for row in load_pool().to_dict("records")[::25]:
        everything = _features(row)
        for skills in (("aim",), ("speed", "reading"), ("flow_aim", "stamina", "accuracy", "sliders", "consistency")):
            assert _features(row, skills) == {k: v for k, v in everything.items() if k in skills}


def test_star_targets_are_the_goals_target_stars():
    # a search leaves out configurations by these, so they must be the ranking's own numbers
    abilities = {"accuracy": 71.0}
    ranked = recommend_modified([], [], 4.39, abilities, "accuracy", ("accuracy",), 0.7, 0.3, frozenset(), {})
    assert star_targets(4.39, 0.7, abilities, "accuracy") == tuple(s.target_stars for s in ranked.goals.values())
    assert star_targets(4.39, 0.7, {}, "accuracy") == ()


def test_a_map_over_another_skills_rating_is_left_out():
    # every rated skill but accuracy, reading and consistency is assessed: no map asks one but the target for more than
    # half a star beyond the rating plus the goal's margin, and those that did are counted by the skill most over
    abilities = dict.fromkeys(SKILLS, 50.0) | {"flow_aim": 30.0}
    skipped = ("aim", "accuracy", "reading", "consistency")
    assert rated_skills("aim", abilities) == ("aim", *(k for k in SKILLS if k not in skipped))
    assert rated_skills("reading", abilities)[0] == "reading"  # the target always is
    result = recommend(load_pool().to_dict("records"), 6.0, abilities, "aim", rated_skills("aim", abilities))
    for stage in result.goals.values():
        assert stage.excluded["Over your Spaced streams rating"] > 0
        for m in stage.maps:
            assert all(b.overload <= OVER for b in m.breakdown.bottlenecks)
    assert any(stage.maps for stage in result.goals.values())


def test_a_skill_a_map_has_no_demand_of_does_not_leave_it_out():
    # no streams: no stamina to ask, so even a stamina rating of 0 keeps the map
    rows = [r for r in load_pool().to_dict("records") if "stamina" not in _features(r)]
    result = recommend(rows, 4.0, {"aim": 50.0, "stamina": 0.0}, "aim", ("aim", "stamina"))
    assert all(not any(r.startswith("Over") for r in stage.excluded) for stage in result.goals.values())
    assert any(stage.maps for stage in result.goals.values())


def test_an_ar_range_keeps_the_maps_with_those_approach_rates():
    pool = load_pool().to_dict("records")
    lo, hi = typical_ar(pool, 6.6)
    assert 8.8 <= lo < hi <= 10.0 and round(hi - lo, 1) == 0.6  # ~9.1-9.7 at 6.6 stars
    assert typical_ar(pool, 3.0)[1] < 9.0  # lower levels read lower AR
    abilities = {"aim": 50.0}
    result = recommend(pool, 6.6, abilities, "aim", ("aim",), ar_range=(9.2, 9.8))
    shown = [m for stage in result.goals.values() for m in stage.maps]
    assert shown and all(9.2 <= m.map["ar"] <= 9.8 for m in shown)
    assert all(stage.excluded["AR outside the chosen range"] > 0 for stage in result.goals.values())
    assert in_ar_range(None, None) and not in_ar_range(None, (9, 10)) and in_ar_range(9.8, (9.2, 9.8))


def test_a_low_consistency_leaves_no_map_out():
    # #149: consistency is rated by how steadily combo and accuracy hold from map to map, not against what maps at the
    # level ask, so a low one (30 here) left out nearly every map; it isn't assessed, and the playlist is the same
    pool = load_pool().to_dict("records")
    steady = {"aim": 58.0, "flow_aim": 46.0, "stamina": 47.0, "sliders": 81.0, "speed": 50.0, "consistency": 81.0}
    shaky = steady | {"consistency": 30.0}
    assert "consistency" not in rated_skills("speed", shaky)
    focus = parse_focus("bpm:120-180,260-270")
    a = recommend(pool, 6.9, steady, "speed", rated_skills("speed", steady), focus=focus)
    b = recommend(pool, 6.9, shaky, "speed", rated_skills("speed", shaky), focus=focus)
    assert [g.eligible for g in a.goals.values()] == [g.eligible for g in b.goals.values()]
    assert all(g.eligible > 0 for g in b.goals.values())
    assert not any("Consistency" in reason for g in b.goals.values() for reason in g.excluded)
