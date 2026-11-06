"""Exact configuration search mechanics and deterministic ranking."""

import pytest

from osu_coach.domain.maps.configuration import SearchOptions
from osu_coach.domain.maps.skillset import _features, _finalize_modified_goals, recommend_modified
from osu_coach.domain.player.algorithm import timing_evidence_eligible
from osu_coach.domain.replays.configuration import Configuration, from_meta
from osu_coach.features.maps.variant_repository import variant_rows
from osu_coach.infra.beatmaps import difficulty
from osu_coach.infra.beatmaps.parser import parse_beatmap_bytes
from osu_coach.infra.map_stats import map_stats
from osu_coach.infra.settings import UserSettings


def test_rate_grid_is_absolute_inclusive_and_configuration_specific():
    options = SearchOptions(True, True, True, 1.10, 2.00)
    configs = options.configurations("a" * 32)
    assert len(configs) == 4 * 92
    assert {c.rate for c in configs if c.dt} == {rate / 100 for rate in range(110, 201)}
    assert Configuration("a" * 32, 64, 1.20).key != Configuration("a" * 32, 64, 1.50).key
    assert Configuration("a" * 32, 8).key != Configuration("a" * 32, 16).key
    assert Configuration("a" * 32, 64, 2.25).rate == 2.25  # replay identity has no grid restriction


def test_custom_hidden_settings_do_not_merge_with_stock_hidden():
    base = {"beatmap_md5": "a" * 32, "mods": 8, "rate": 1.0, "client": "lazer"}
    ordinary = from_meta({**base, "lazer_mods": [{"acronym": "HD"}]})
    customized = from_meta(
        {**base, "lazer_mods": [{"acronym": "HD", "settings": {"only_fade_approach_circles": True}}]}
    )
    assert ordinary.key != customized.key


def test_stock_lazer_mod_descriptors_and_nightcore_share_exact_configuration():
    md5 = "a" * 32
    canonical = Configuration(md5, 8 | 64, 1.20, "lazer")
    replay = from_meta(
        {
            "beatmap_md5": md5,
            "mods": 8 | 512,
            "rate": 1.20,
            "client": "lazer",
            "lazer_mods": [
                {"acronym": "HD", "settings": {}},
                {"acronym": "NC", "settings": {"speed_change": 1.20}},
            ],
        }
    )
    assert replay.key == canonical.key
    assert Configuration(md5, 64 | 512, 1.20).key == Configuration(md5, 64, 1.20).key
    inferred = from_meta(
        {
            "beatmap_md5": md5,
            "client": "lazer",
            "lazer_mods": [{"acronym": "HD"}, {"acronym": "DT", "settings": {"speed_change": 1.20}}],
        }
    )
    assert inferred.key == canonical.key
    custom = from_meta(
        {
            "beatmap_md5": md5,
            "mods": 8 | 64,
            "rate": 1.20,
            "client": "lazer",
            "lazer_mods": [{"acronym": "HD", "settings": {"only_fade_approach_circles": True}}],
        }
    )
    assert custom.key != canonical.key


@pytest.mark.parametrize("rate", [1.099, 2.001, float("nan")])
def test_invalid_rate_bounds_are_rejected(rate):
    with pytest.raises(ValueError):
        SearchOptions(adjustable_dt=True, min_rate=rate)


def test_dt_timing_gate_is_strict_and_does_not_gate_other_mods():
    assert not timing_evidence_eligible(64, 0.88)
    assert timing_evidence_eligible(64, 0.8800001)
    assert not timing_evidence_eligible(512, 0.88)
    assert timing_evidence_eligible(0, 0.5)


def test_reading_terms_are_added_once():
    row = {"density_p90": 6, "odd_rhythm_share": 0.1, "ar": 10.0}
    ordinary = _features(row)["reading"]
    hidden = _features({**row, "mods": "HD"})["reading"]
    assert ordinary == pytest.approx(6 * 1.1)
    assert hidden > ordinary


def test_stamina_uses_real_section_duration_and_rest_with_tempo():
    base = {
        "stream_bpm": 180,
        "stream_notes": 100,
        "max_run": 32,
        "drain_length": 120,
        "run_duration_p90": 10,
        "run_rest_median": 2,
    }
    fast = {**base, "stream_bpm": 216, "drain_length": 100, "run_duration_p90": 10 / 1.2, "run_rest_median": 2 / 1.2}
    ordinary = _features(base)["stamina"]
    quicker = _features(fast)["stamina"]
    assert ordinary < quicker < ordinary * 1.2


def _row(md5: str, stars: float) -> dict:
    return {
        "md5": md5,
        "beatmap_id": 1,
        "beatmapset_id": 1,
        "artist": "a",
        "title": "t",
        "version": "v",
        "stars": stars,
        "cs": 4,
        "jump_velocity": 0.25,
        "sharp_share": 0.2,
        "s_aim": 0.8,
        "aim": 2.0,
        "rate": 1.0,
        "mods": "NM",
    }


def test_transformed_star_entry_stable_tie_and_empty_set():

    base = [_row(f"{i:032x}", 4.0) for i in range(20)] + [_row("f" * 32, 2.0)]
    variants = [
        {**_row("f" * 32, 4.0), "configuration_id": "b", "mods": "DT", "rate": 1.2},
        {**_row("e" * 32, 4.0), "configuration_id": "a", "mods": "DT", "rate": 1.2},
    ]
    result = recommend_modified(base, variants, 4.0, {"aim": 50}, "aim", ("aim",), 0.5, 0.3, frozenset(), {})
    comfort = result["goals"]["Comfort"]
    assert comfort["eligible"] == 2
    assert [r["configuration_id"] for r in comfort["maps"]] == ["a", "b"]
    empty = recommend_modified(
        base, [{**variants[0], "stars": 8.0}], 4.0, {"aim": 50}, "aim", ("aim",), 0.5, 0.3, frozenset(), {}
    )
    assert empty["goals"]["Comfort"]["maps"] == []
    assert empty["goals"]["Comfort"]["excluded"]["Outside star window"] == 1


def test_modified_search_keeps_best_configuration_per_map_before_limit():

    base = [_row(f"{i:032x}", 4.0) for i in range(20)]
    repeated = "f" * 32
    variants = [
        {**_row(repeated, 4.10), "configuration_id": "dt@1.32", "mods": "DT", "rate": 1.32},
        {**_row(repeated, 4.00), "configuration_id": "dt@1.33", "mods": "DT", "rate": 1.33},
        {**_row(repeated, 4.00), "configuration_id": "hd@1.33", "mods": "HDDT", "rate": 1.33},
        {**_row("e" * 32, 4.05), "configuration_id": "other", "mods": "DT", "rate": 1.30},
        {**_row("d" * 32, 4.15), "configuration_id": "third", "mods": "DT", "rate": 1.30},
    ]
    result = recommend_modified(base, variants, 4.0, {"aim": 50}, "aim", ("aim",), 0.5, 0.3, frozenset(), {}, limit=2)
    comfort = result["goals"]["Comfort"]
    assert result["candidate_count"] == len(variants)
    assert comfort["eligible"] == 3
    assert [row["md5"] for row in comfort["maps"]] == [repeated, "e" * 32]
    assert comfort["maps"][0]["configuration_id"] == "dt@1.33"  # better score than 1.32, tie beats HD


@pytest.mark.parametrize(
    ("rates", "expected"),
    [
        ({"Warm-up": 1.10, "Comfort": 1.20, "Push": 1.35}, {"Push"}),
        ({"Warm-up": 1.10, "Comfort": 1.20, "Push": 1.33}, {"Comfort"}),
        ({"Warm-up": 1.10, "Comfort": 1.24}, {"Comfort"}),
        ({"Warm-up": 1.10, "Comfort": 1.25}, {"Comfort"}),
        ({"Warm-up": 1.10, "Comfort": 1.26}, {"Warm-up", "Comfort"}),
        ({"Comfort": 1.20, "Push": 1.34}, {"Comfort"}),
        ({"Comfort": 1.20, "Push": 1.35}, {"Push"}),
        ({"Warm-up": 1.10, "Push": 1.25}, {"Push"}),
        ({"Warm-up": 1.10, "Push": 1.26}, {"Warm-up", "Push"}),
    ],
)
def test_modified_stage_assignment_respects_rate_gaps(rates, expected):
    md5 = "f" * 32
    goals = {goal: {"eligible": 0, "maps": [], "excluded": {}} for goal in ("Warm-up", "Comfort", "Push")}
    best = {
        goal: {md5: {"md5": md5, "rate": rates[goal], "formula_score": 0.0, "configuration_id": goal}}
        if goal in rates
        else {}
        for goal in goals
    }
    _finalize_modified_goals(goals, best, 100)
    assert {goal for goal, data in goals.items() if data["maps"]} == expected
    assert all(data["eligible"] == len(data["maps"]) for data in goals.values())
    for goal in rates.keys() - expected:
        assert goals[goal]["excluded"]["Shown in another stage"] == 1


def test_history_is_configuration_specific():

    base = [_row(f"{i:032x}", 4.0) for i in range(20)]
    variants = [{**_row("f" * 32, 4.0), "configuration_id": "hd@1.20", "mods": "HDDT", "rate": 1.2}]
    result = recommend_modified(
        base, variants, 4.0, {"aim": 50}, "aim", ("aim",), 0.5, 0.3, frozenset(), {"hd@1.20": 1.1}
    )
    breakdown = result["goals"]["Comfort"]["maps"][0]["breakdown"]
    assert breakdown["history"] == 1.1
    assert breakdown["terms"]["history"] > 0


@pytest.mark.parametrize(
    ("abilities", "assessed", "reason"),
    [
        ({}, ("aim",), "Target player rating unknown"),
        ({"aim": 50}, ("aim", "reading"), "Assessed player rating unknown"),
    ],
)
def test_missing_ratings_produce_explicit_empty_stages(abilities, assessed, reason):

    base = [_row(f"{i:032x}", 4.0) for i in range(20)]
    variants = [{**_row("f" * 32, 4.0), "configuration_id": "one"}]
    result = recommend_modified(base, variants, 4.0, abilities, "aim", assessed, 0.5, 0.3, frozenset(), {})
    for stage in result["goals"].values():
        assert stage["eligible"] == 0
        assert stage["maps"] == []
        assert stage["excluded"] == {reason: 1}


@pytest.mark.parametrize(
    ("ratings", "assessed", "reason"),
    [(None, "aim", "Target player rating unknown"), ('{"aim":50}', "aim,reading", "Assessed player rating unknown")],
)
def test_missing_rating_search_skips_map_retrieval_and_reports_zero_coverage(
    monkeypatch, tmp_path, ratings, assessed, reason
):
    from types import SimpleNamespace

    import pandas as pd

    from osu_coach.features.maps import service
    from osu_coach.features.maps.schemas import PlaylistSearchRequest

    pool = pd.DataFrame([_row("a" * 32, 4.0)])
    ws = SimpleNamespace(
        pool=lambda: pool,
        profile=lambda: None,
        settings=lambda: UserSettings(),
        library=None,
        check_library=None,
        preferred_client=lambda: "stable",
        plays=[],
        cache_dir=tmp_path,
    )

    def unexpected_retrieval(*args):
        raise AssertionError("Missing player ratings must not trigger .osu retrieval")

    monkeypatch.setattr(service, "verified_bytes", unexpected_retrieval)
    result = service.search(
        ws,
        PlaylistSearchRequest(skill="aim", comfort=4, ratings=ratings, assessed=assessed, allow_hr=True),
        lambda *_: None,
    )
    assert result.coverage_maps == 0
    assert result.unavailable_maps == 0
    assert result.calculator_unavailable_maps == 0
    assert result.unavailable_configurations == 0
    assert all(stage.excluded == {reason: 1} and not stage.maps for stage in result.stages)


@pytest.mark.skipif(not difficulty.available(), reason="rosu-pp-py not installed")
def test_exact_engine_stars_and_single_rate_application(res):
    raw = res("maps/0619c930348063c2a967a3af4d69cd6b.osu").read_bytes()
    bm = parse_beatmap_bytes(raw)
    nm = map_stats(bm, raw)
    custom = map_stats(bm, raw, 16 | 64, 1.20)
    standard = map_stats(bm, raw, 64, 1.50)
    assert custom["cs"] == pytest.approx(min(10, bm.cs * 1.3))
    assert custom["hp"] == pytest.approx(min(10, bm.hp * 1.4))
    assert custom["stars"] == difficulty.attributes(raw, 16 | 64, 1.20)["stars"]
    assert standard["stars"] == difficulty.attributes(raw, 64)["stars"]
    assert custom["bpm"] == pytest.approx(nm["bpm"] * 1.2)
    assert custom["drain_length"] == pytest.approx(nm["drain_length"] / 1.2)
    assert custom["hit300_ms"] < nm["hit300_ms"]
    assert custom["ar"] > bm.ar
    assert standard["density_p90"] == nm["density_p90"]


@pytest.mark.skipif(not difficulty.available(), reason="rosu-pp-py not installed")
def test_variant_cache_separates_custom_rates(res, tmp_path):
    raw = res("maps/0619c930348063c2a967a3af4d69cd6b.osu").read_bytes()
    md5 = "0619c930348063c2a967a3af4d69cd6b"
    configs = (Configuration(md5, 64, 1.20), Configuration(md5, 64, 1.50))
    first = list(variant_rows(tmp_path, raw, configs))
    again = list(variant_rows(tmp_path, raw, configs))
    assert len(first) == 2 and first == again
    assert first[0]["configuration_id"] != first[1]["configuration_id"]
    assert first[0]["stars"] != first[1]["stars"]


@pytest.mark.skipif(not difficulty.available(), reason="rosu-pp-py not installed")
def test_variant_cache_counts_failed_configurations_even_when_map_partly_available(res, tmp_path, monkeypatch):
    raw = res("maps/0619c930348063c2a967a3af4d69cd6b.osu").read_bytes()
    md5 = "0619c930348063c2a967a3af4d69cd6b"
    configs = (Configuration(md5), Configuration(md5, 64, 1.20))
    from osu_coach.infra.map_stats import finish_stats

    def sometimes_unavailable(pattern, data, mods=0, rate=1.0, *, lazer=False, parsed_map=None):
        return None if rate == 1.20 else finish_stats(pattern, data, mods, rate, lazer=lazer, parsed_map=parsed_map)

    monkeypatch.setattr("osu_coach.features.maps.variant_repository.finish_stats", sometimes_unavailable)
    counts = []
    assert len(list(variant_rows(tmp_path, raw, configs, on_unavailable=counts.append))) == 1
    assert counts == [1]
    assert len(list(variant_rows(tmp_path, raw, configs, on_unavailable=counts.append))) == 1
    assert counts == [1, 1]
