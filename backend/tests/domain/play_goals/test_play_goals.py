from copy import deepcopy
from dataclasses import replace

import pandas as pd
import pytest

from osu_coach.domain.analysis.events import Events, events
from osu_coach.domain.analysis.models import ReplayMeta
from osu_coach.domain.play_goals.evidence import (
    accuracy_range,
    configuration,
    full_combo,
    skipped_attempts,
)
from osu_coach.domain.play_goals.models import EvidenceRow, GoalPlay
from osu_coach.domain.play_goals.reachability import reachability
from osu_coach.domain.play_goals.recommend import dynamics, lacking_focus, recommend, sampled_pp
from tests.conftest import play_of


def target(**changes):
    return {
        "md5": "target",
        "mods": "NM",
        "client": "stable",
        "stars": 4.0,
        "ar": 9,
        "od": 8,
        "bpm": 180,
        "length_s": 120,
        "stream_share": 0.1,
        "jump_share": 0.3,
        **changes,
    }


def row(**changes) -> EvidenceRow:
    values = {
        "key": "",
        "beatmap_md5": "map-0",
        "date": "2026-10-01",
        "client": "stable",
        "mods_name": "NM",
        "completed": True,
        "n_played": 100,
        "n_objects": 100,
        "stars": 4.0,
        "ar": 9,
        "od": 8,
        "bpm": 180,
        "length_s": 120,
        "accuracy": 0.94,
        "aim": float("nan"),
        "speed": float("nan"),
        "fc": False,
        "breaks": 2,
        "stream_share": 0.1,
        "jump_share": 0.3,
    }
    return EvidenceRow(**{**values, **changes})


def plays(count=10, maps=5, **changes):
    return [
        row(
            **{
                "key": f"k{i}",
                "beatmap_md5": f"map-{i % maps}",
                "accuracy": 0.94 + i * 0.004,
                "date": f"2026-10-{i + 1:02}",
                **changes,
            }
        )
        for i in range(count)
    ]


def meta(**values) -> ReplayMeta:
    return ReplayMeta.from_dict({"key": "k", **values})


def goal_play(key="k", lazer_mods=None, **values) -> GoalPlay:
    return GoalPlay(key, meta(key=key, **values), Events.from_columns({}, n=0), lazer_mods=lazer_mods)


def test_accuracy_gate_counts_plays_and_distinct_maps():
    assert accuracy_range(target(), plays(9)) is None
    assert accuracy_range(target(), plays(10, 4)) is None
    estimate = accuracy_range(target(), plays())
    assert estimate.maps == 5 and estimate.plays == 10
    assert 0.94 <= estimate.low <= estimate.median <= estimate.high <= 1
    assert accuracy_range(target(), plays(100, 1)) is None


def test_accuracy_does_not_mix_mods_clients_failures_or_distant_patterns():
    for changes in (
        {"mods_name": "HD"},
        {"client": "lazer"},
        {"completed": False},
        {"n_played": 99},
        {"stars": 8},
        {"stream_share": 0.9},
    ):
        assert accuracy_range(target(), plays(**changes)) is None


def test_configuration_identity_checks_exact_lazer_settings_and_normalizes_nc():
    lazer = meta(mods=0, rate=1.0, client="lazer")
    assert configuration(lazer) is None
    assert configuration(lazer, []) == "NM"
    assert configuration(meta(mods=576, rate=1.5, client="stable")) == "DT"
    for settings in ({"speed_change": 1.2}, {"adjust_pitch": True}):
        dt = meta(mods=64, rate=1.5, client="lazer")
        assert configuration(dt, [{"acronym": "DT", "settings": settings}]) is None
    assert configuration(meta(mods=128, rate=1, client="stable")) is None


def test_extreme_target_honest_without_extrapolated_accuracy():
    reach = reachability(target(stars=9, bpm=240, stream_share=0.5), plays())
    assert reach.verdict == "beyond"
    assert reach.reasons and reach.confidence == "limited"
    assert accuracy_range(target(stars=9), plays()) is None


def test_close_to_fc_needs_verified_complete_same_configuration():
    rows = plays()
    rows.append(replace(rows[0], beatmap_md5="target", breaks=1))
    assert reachability(target(), rows).verdict == "fc_near"
    rows[-1] = replace(rows[-1], fc=True)
    assert reachability(target(), rows).verdict == "fc_done"
    assert reachability(target(mods="HD"), rows).verdict == "unknown"


def test_stars_alone_do_not_prove_a_target_is_beyond_reach():
    assert reachability(target(stars=9), plays()).verdict == "unknown"


def test_fc_requires_all_notes_and_no_slider_break_not_just_zero_misses():
    objects = pd.DataFrame(
        [
            {
                "kind": "slider",
                "played": True,
                "result": 300,
                "head_hit": True,
                "broke": False,
                "time": 1000,
                "idx": 0,
                "pattern": "slider",
                "stream_bpm": None,
            }
        ]
    )
    m = meta(completed=True, n_played=1, n_objects=1, nmiss=0, sim_match=True)
    a = GoalPlay("k", m, events(play_of({"key": "k"}, objects).notes))
    assert full_combo(a)
    broken = objects.assign(broke=[True] + [False] * (len(objects) - 1), break_reason="follow")
    assert not full_combo(GoalPlay("k", m, events(play_of({"key": "k"}, broken).notes)))
    assert not full_combo(GoalPlay("k", replace(m, n_played=0), a.events))


def pool():
    return [
        {
            **target(md5=f"{i:032x}"),
            "status": "ranked",
            "s_aim": 0.8,
            "pp_curve": [{"accuracy": 0.9, "pp": 60}, {"accuracy": 0.95, "pp": 100}, {"accuracy": 0.99, "pp": 150}],
        }
        for i in range(6)
    ]


def test_farming_does_not_promote_theoretical_pp_to_achievable_forecast():
    recommendations = recommend(pool(), plays(), "farm", ["NM"], "stable", None, [])
    assert recommendations and all(not r.projected and r.pp is not None for r in recommendations)
    assert recommend([{**pool()[0], "status": "loved"}], plays(), "farm", ["NM"], "stable", None, []) == []


def test_supported_fc_evidence_allows_achievable_scenario_and_keeps_repeats():
    rows = plays(fc=True)
    rows[0] = replace(rows[0], beatmap_md5=pool()[0]["md5"])
    recommendations = recommend(pool(), rows, "farm", ["NM"], "stable", None, [])
    assert any(r.projected for r in recommendations)
    assert any(r.map["md5"] == rows[0].beatmap_md5 for r in recommendations)
    assert len({r.map["md5"] for r in recommendations[:5]}) == 5


def test_play_target_scales_with_difficulty_without_estimate():
    maps = [{**pool()[0], "stars": 1.6}, {**pool()[1], "stars": 1.0}]
    targets = {r.map["stars"]: r.practice_accuracy for r in recommend(maps, [], "mod", ["NM"], "stable", None, [])}
    assert targets == {1.6: 0.93, 1.0: 0.95}
    far_below = {**pool()[2], "stars": 0.2}
    assert recommend([far_below], [], "mod", ["NM"], "stable", None, [])[0].practice_accuracy == 0.99


def test_skipped_attempts_explain_why_same_map_plays_are_unused():
    def attempt(key, **values):
        return goal_play(key, beatmap_md5="target", player="me", mod_string="NM", **values)

    analyses = [
        attempt("a", client="lazer", sim_match=True),
        attempt("b", client="stable", sim_match=False),
        attempt("c", client="stable", sim_match=True, mods=0, rate=1),
    ]
    why = skipped_attempts(analyses, [row(key="c")], "me", target())
    assert sum(why.values()) == 2
    assert {r.code for r in why} == {"other_client", "sim_mismatch"}
    assert not skipped_attempts(analyses[2:], [row(key="c")], "me", target())


def test_single_same_map_attempt_gives_a_verdict():
    one = row(beatmap_md5="target", completed=True, breaks=40, accuracy=0.9)
    assert reachability(target(), [one]).verdict == "beyond_for_now"
    assert reachability(target(), [replace(one, breaks=5)]).verdict == "stretch"


def test_dynamics_and_lacking_focus_follow_the_weakest_demanded_skill():
    assert dynamics({"s_speed": 0.8, "s_aim": 0.2, "s_reading": 0.1}) == ["speed"]
    assert dynamics({"s_aim": 0.7, "s_reading": 0.6}) == ["aim", "reading"]
    assert dynamics({"s_aim": 0.1}) == []
    mixed = {"s_speed": 0.8, "s_aim": 0.7}
    assert lacking_focus(mixed, {"speed": 0.9, "aim": 0.2})[0] == "aim"
    assert lacking_focus(mixed, {"speed": 0.2, "aim": 0.9})[0] == "speed"


def test_verdict_uses_recent_attempts_not_a_stale_best():
    old = row(beatmap_md5="target", breaks=1, date="2022-01-01")
    new = [replace(old, breaks=30, date=f"2026-10-0{i}") for i in range(1, 4)]
    assert reachability(target(), [old, *new]).verdict == "beyond_for_now"


def test_nofail_does_not_change_the_configuration():
    assert configuration(meta(mods=1, client="stable", rate=1)) == "NM"
    assert configuration(meta(mods=65, client="stable", rate=1.5)) == "DT"
    assert configuration(meta(mods=1, client="lazer", rate=1), [{"acronym": "NF"}]) == "NM"


def test_maps_can_have_several_dynamics():
    assert dynamics({"s_speed": 0.9, "s_aim": 0.5, "s_reading": 0.1}) == ["speed", "aim"]
    assert dynamics({"s_aim": 0.9, "s_speed": 0.1}) == ["aim"]
    assert dynamics({"s_stamina": 0.8, "s_speed": 0.4}) == ["stamina", "speed"]
    assert lacking_focus({"s_stamina": 0.8}, {"stamina": 0.2})[0] == "stamina"


def test_minimum_pp_hides_low_pp_maps_and_inflated_mod_maps_stay_out():
    nm = {**pool()[0], "stars": 1.5}
    dt = {**nm, "mods": "DT", "stars": 4.0}  # DT turns an easy map into one far above a starter level
    assert [r.map["mods"] for r in recommend([nm, dt], [], "farm", ["NM", "DT"], "stable", None, [])] == ["NM"]
    assert recommend([nm], [], "farm", ["NM"], "stable", None, [], min_pp=50)
    assert recommend([nm], [], "farm", ["NM"], "stable", None, [], min_pp=5000) == []


def test_pp_at_target_is_interpolated_between_curve_points():
    curve = {"pp_curve": [{"accuracy": 0.95, "pp": 100}, {"accuracy": 0.99, "pp": 144}]}
    assert sampled_pp(curve, 0.95) == (100, 0.95)
    pp, accuracy = sampled_pp(curve, 0.97)
    assert accuracy == 0.97 and pp == pytest.approx(120, abs=0.01)  # geometric mean of 100 and 144
    assert sampled_pp(curve, 0.90) is None and sampled_pp(curve, 1.0) is None


def test_level_is_the_profile_comfort_stars():
    hard = {**pool()[0], "stars": 5.8}
    easy = {**pool()[1], "stars": 3.5}
    got = recommend([hard, easy], [], "mod", ["NM"], "stable", None, [], comfort=4.0)
    assert [r.map["stars"] for r in got] == [3.5]
    assert got[0].practice_accuracy == 0.93  # no plays of this difficulty: the fixed scale


def test_target_follows_nearly_clean_plays_of_similar_difficulty():
    clean = plays(6, maps=6, stars=4.0, accuracy=0.96, breaks=0)
    sloppy = [replace(r, beatmap_md5=f"sloppy-{i}") for i, r in enumerate(plays(6, maps=6, accuracy=0.80, breaks=20))]
    easy = {**pool()[1], "stars": 3.8}
    got = recommend([easy], clean + sloppy, "mod", ["NM"], "stable", None, [], comfort=4.5)
    assert got[0].practice_accuracy == 0.95  # halfway between the difficulty scale (93%) and clean plays (97%)


def test_unrelated_maps_do_not_replace_targeted_practice():
    assert recommend(deepcopy(pool()), plays(), "fc", ["NM"], "stable", target(), ["speed"]) == []
