from copy import deepcopy
from types import SimpleNamespace

import pandas as pd
import pytest

from osu_coach.play_goals import domain


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


def plays(count=10, maps=5, **changes):
    return [
        {
            "beatmap_md5": f"map-{i % maps}",
            "mods_name": "NM",
            "client": "stable",
            "completed": True,
            "n_played": 100,
            "n_objects": 100,
            "stars": 4.0,
            "ar": 9,
            "od": 8,
            "bpm": 180,
            "length_s": 120,
            "stream_share": 0.1,
            "jump_share": 0.3,
            "accuracy": 0.94 + i * 0.004,
            "fc": False,
            "breaks": 2,
            "date": f"2026-10-{i + 1:02}",
            **changes,
        }
        for i in range(count)
    ]


@pytest.mark.parametrize(
    "value, expected",
    [
        ("1234", 1234),
        ("https://osu.ppy.sh/b/1234", 1234),
        ("https://osu.ppy.sh/beatmaps/1234", 1234),
        ("https://osu.ppy.sh/beatmapsets/5#osu/1234", 1234),
    ],
)
def test_target_ids(value, expected):
    assert domain.beatmap_id(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.test/b/1234",
        "https://osu.ppy.sh/beatmapsets/5",
        "https://osu.ppy.sh/beatmapsets/5#mania/1234",
        "file:///etc/passwd",
        "0",
    ],
)
def test_rejects_non_difficulty_and_arbitrary_urls(value):
    with pytest.raises(ValueError):
        domain.beatmap_id(value)


def test_accuracy_gate_counts_plays_and_distinct_maps():
    assert domain.accuracy_range(target(), plays(9)) is None
    assert domain.accuracy_range(target(), plays(10, 4)) is None
    estimate = domain.accuracy_range(target(), plays())
    assert estimate["maps"] == 5 and estimate["plays"] == 10
    assert 0.94 <= estimate["low"] <= estimate["median"] <= estimate["high"] <= 1
    assert domain.accuracy_range(target(), plays(100, 1)) is None


def test_accuracy_does_not_mix_mods_clients_failures_or_distant_patterns():
    for changes in (
        {"mods_name": "HD"},
        {"client": "lazer"},
        {"completed": False},
        {"n_played": 99},
        {"stars": 8},
        {"stream_share": 0.9},
    ):
        assert domain.accuracy_range(target(), plays(**changes)) is None


def test_configuration_identity_checks_exact_lazer_settings_and_normalizes_nc():
    meta = {"mods": 0, "rate": 1.0, "client": "lazer"}
    assert domain.configuration(meta) is None
    assert domain.configuration({**meta, "goal_lazer_mods": []}) == "NM"
    assert domain.configuration({"mods": 576, "rate": 1.5, "client": "stable"}) == "DT"
    for settings in ({"speed_change": 1.2}, {"adjust_pitch": True}):
        assert (
            domain.configuration(
                {
                    "mods": 64,
                    "rate": 1.5,
                    "client": "lazer",
                    "goal_lazer_mods": [{"acronym": "DT", "settings": settings}],
                }
            )
            is None
        )
    assert domain.configuration({"mods": 128, "rate": 1, "client": "stable"}) is None


def test_extreme_target_honest_without_extrapolated_accuracy():
    verdict, reasons, confidence = domain.reachability(target(stars=9, bpm=240, stream_share=0.5), plays())
    assert verdict == "Beyond current reach"
    assert reasons and confidence == "limited"
    assert domain.accuracy_range(target(stars=9), plays()) is None


def test_close_to_fc_needs_verified_complete_same_configuration():
    rows = plays()
    rows.append({**rows[0], "beatmap_md5": "target", "breaks": 1})
    assert domain.reachability(target(), rows)[0] == "FC looks within reach"
    rows[-1]["fc"] = True
    assert domain.reachability(target(), rows)[0] == "Already FCed"
    assert domain.reachability(target(mods="HD"), rows)[0] == "Not enough evidence"


def test_stars_alone_do_not_prove_a_target_is_beyond_reach():
    assert domain.reachability(target(stars=9), plays())[0] == "Not enough evidence"


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
    a = SimpleNamespace(
        meta={"completed": True, "n_played": 1, "n_objects": 1, "nmiss": 0, "sim_match": True}, objects=objects
    )
    assert domain.full_combo(a)
    a.objects.loc[0, "broke"] = True
    a.objects["break_reason"] = "follow"
    assert not domain.full_combo(a)
    a.objects.loc[0, "broke"] = False
    a.meta["n_played"] = 0
    assert not domain.full_combo(a)


def pool():
    return [
        {
            **target(md5=f"{i:032x}"),
            "status": "ranked",
            "s_aim": 0.8,
            "pp_curve": [{"accuracy": 0.95, "pp": 100}, {"accuracy": 0.99, "pp": 150}],
        }
        for i in range(6)
    ]


def test_farming_does_not_promote_theoretical_pp_to_achievable_forecast():
    recommendations = domain.recommend(pool(), plays(), "farm", ["NM"], "stable", None, [])
    assert recommendations and all(not r["_projected"] for r in recommendations)
    assert all(r["pp_label"].startswith("Conditional") for r in recommendations)
    assert domain.recommend([{**pool()[0], "status": "loved"}], plays(), "farm", ["NM"], "stable", None, []) == []


def test_supported_fc_evidence_allows_achievable_scenario_and_keeps_repeats():
    rows = plays(fc=True)
    rows[0]["beatmap_md5"] = pool()[0]["md5"]
    recommendations = domain.recommend(pool(), rows, "farm", ["NM"], "stable", None, [])
    assert any(r["_projected"] for r in recommendations)
    assert any(r["map"]["md5"] == rows[0]["beatmap_md5"] for r in recommendations)
    assert len({r["map"]["md5"] for r in recommendations[:5]}) == 5


def test_unrelated_maps_do_not_replace_targeted_practice():
    candidates = deepcopy(pool())
    assert (
        domain.recommend(
            candidates, plays(), "fc", ["NM"], "stable", target(), [{"skill": "speed", "title": "Stream control"}]
        )
        == []
    )
