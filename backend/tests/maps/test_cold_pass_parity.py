"""Exact output parity between the accelerated and independent map passes."""

from pathlib import Path

import pytest

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
