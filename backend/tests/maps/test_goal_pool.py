import gzip
import json

import pytest

from osu_coach.beatmaps.performance import CALCULATOR_VERSION
from osu_coach.maps.goal_pool import CONFIGS
from osu_coach.maps.goal_repository import GOAL_POOL, load_goal_pool


def test_shipped_offline_data_covers_configs_clients_and_star_bands():
    rows = load_goal_pool()
    assert len({r["md5"] for r in rows}) >= 40
    assert {r["mods"] for r in rows} == set(CONFIGS)
    assert {r["client"] for r in rows} == {"stable", "lazer"}
    assert min(r["stars"] for r in rows) < 1.5
    assert max(r["stars"] for r in rows) > 8
    for row in rows:
        assert row["status"] in ("ranked", "approved") and row["beatmap_id"] > 0
        assert row["pp_curve"] and all(p["pp"] >= 0 and 0 <= p["accuracy"] <= 1 for p in row["pp_curve"])
    document = json.loads(gzip.decompress(GOAL_POOL.read_bytes()))
    assert document["calculator_version"] == CALCULATOR_VERSION
    assert document["coverage_maps"] == len(rows) // (len(CONFIGS) * 2)


def test_incompatible_pool_is_not_silently_accepted(tmp_path):
    path = tmp_path / "pool.gz"
    path.write_bytes(gzip.compress(json.dumps({"schema_version": 0, "calculator_version": "old"}).encode()))
    with pytest.raises(ValueError, match="rebuilt"):
        load_goal_pool(path)
