"""Exact output parity between the accelerated and independent map passes."""

from pathlib import Path

import pytest

from osu_coach.beatmaps import difficulty
from osu_coach.beatmaps.parser import parse_beatmap_bytes
from osu_coach.maps.configuration import SearchOptions
from osu_coach.maps.domain import map_stats
from osu_coach.maps.variant_repository import _clean, variant_rows

MAPS = Path(__file__).resolve().parents[1] / "resources" / "maps"


@pytest.mark.parametrize("md5", ("0619c930348063c2a967a3af4d69cd6b", "e0d805c891bf0e18ecb543435c6625f7"))
@pytest.mark.parametrize("client", ("stable", "lazer"))
def test_cold_pass_matches_direct_map_stats(tmp_path, md5, client):
    raw = (MAPS / f"{md5}.osu").read_bytes()
    bm = parse_beatmap_bytes(raw)
    configs = SearchOptions(True, True, True).configurations(md5, client=client)
    configs = tuple(c for c in configs if c.rate in (1.0, 1.10, 1.33, 1.50, 1.99, 2.0))
    rows = list(variant_rows(tmp_path, raw, configs))
    assert len(rows) == len(configs)
    for config, row in zip(configs, rows):
        key = row["configuration_id"]
        stats = {k: v for k, v in row.items() if k not in ("configuration_id", "mods", "rate")}
        expected = _clean(map_stats(bm, raw, config.mods, config.rate, lazer=config.client == "lazer"))
        assert stats == expected, key
    assert list(variant_rows(tmp_path, raw, configs)) == rows


@pytest.mark.skipif(not difficulty.available(), reason="rosu-pp-py not installed")
@pytest.mark.parametrize("client", ("stable", "lazer"))
def test_full_grid_reuses_one_rosu_map_without_changing_results(tmp_path, monkeypatch, client):
    md5 = "0619c930348063c2a967a3af4d69cd6b"
    raw = (MAPS / f"{md5}.osu").read_bytes()
    bm = parse_beatmap_bytes(raw)
    configs = SearchOptions(True, True, True).configurations(md5, client=client)
    original_map = difficulty._map
    parses = []

    def counted_map(data):
        parses.append(data)
        return original_map(data)

    monkeypatch.setattr(difficulty, "_map", counted_map)
    rows = list(variant_rows(tmp_path, raw, configs))
    assert parses == [raw]
    monkeypatch.setattr(difficulty, "_map", original_map)
    assert len(rows) == len(configs)
    for config, row in zip(configs, rows):
        stats = {k: v for k, v in row.items() if k not in ("configuration_id", "mods", "rate")}
        expected = _clean(map_stats(bm, raw, config.mods, config.rate, lazer=config.client == "lazer"))
        assert stats == expected, config.key
    assert list(variant_rows(tmp_path, raw, configs)) == rows


def test_failed_rosu_parse_caches_unavailable_configs(tmp_path, monkeypatch):
    md5 = "0619c930348063c2a967a3af4d69cd6b"
    raw = (MAPS / f"{md5}.osu").read_bytes()
    configs = SearchOptions(True, True, True).configurations(md5)[:4]
    monkeypatch.setattr(difficulty, "parse_map", lambda _raw: None)
    unavailable = []
    assert list(variant_rows(tmp_path, raw, configs, on_unavailable=unavailable.append)) == []
    assert unavailable == [len(configs)]
    assert list(variant_rows(tmp_path, raw, configs)) == []
