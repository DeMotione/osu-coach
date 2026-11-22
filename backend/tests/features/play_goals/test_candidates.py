"""The play goals' maps: the whole pool, read from its map table and pp table, without .osu files."""

import math

import numpy as np
import pytest

from osu_coach.domain.maps.variants import configuration_columns, pool_maps
from osu_coach.domain.play_goals.recommend import Level
from osu_coach.features.play_goals.candidates import Wanted, candidates
from osu_coach.infra.map_pool import load_pool
from osu_coach.infra.pp_table import load_pp_table
from osu_coach.infra.variant_table import load_table


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    table = load_table(tmp_path_factory.mktemp("cache"))
    assert table is not None, "the bundled variant table is stale: run backend/tools/build_variant_table.py"
    return table, load_pool(), load_pp_table()


def test_a_custom_speed_reads_the_tables_rows_in_the_level_window(sources):
    table, pool, pp = sources
    level = Level(stars=5.0, measured=True, lowest=3.5, highest=5.5)
    rows = candidates(table, pool, pp, [Wanted("HDDT 1.20x", "HDDT", 1.2, level)], "lazer", "mod", [])
    assert 100 <= len(rows) <= 600
    assert {(r["config"], r["mods"], r["rate"], r["client"]) for r in rows} == {("HDDT 1.20x", "HDDT", 1.2, "lazer")}
    assert all(3.5 <= r["stars"] <= 5.5 for r in rows)
    assert all(r["pp_curve"] is None for r in rows)  # pp: Farm PP's, at the combinations' own speed
    # the nearest to the level come first: |delta + 0.3| is what the other goals rank by without skills in focus
    assert sorted(abs(r["stars"] - 5.0 + 0.3) for r in rows)[-1] <= 1.2
    one = rows[0]
    maps, record_of = pool_maps(table, pool["md5"].astype(str).tolist())
    t = table.index[one["md5"]]
    stored = configuration_columns(table, np.array([t]), False, True, 1.2, ("stars",))["stars"][0]
    assert one["stars"] == pytest.approx(stored) and one["stars_nm"] == pool.loc[record_of[t], "stars"]
    assert one["length_s"] == one["drain_length"] and math.isfinite(one["s_speed"])


def test_farm_pp_reads_only_ranked_maps_with_their_pp(sources):
    table, pool, pp = sources
    level = Level(stars=4.0, measured=False, lowest=2.5, highest=4.2)
    wanted = [Wanted("NM", "NM", 1.0, level), Wanted("DT", "DT", 1.5, level)]
    rows = candidates(table, pool, pp, wanted, "stable", "farm", [], limit=200)
    assert len(rows) == 200 and {r["config"] for r in rows} <= {"NM", "DT"}
    assert all(r["status"] in ("ranked", "approved") and r["pp_curve"] for r in rows)
    # not measured: the map without mods may not be above the level either
    assert all(r["stars_nm"] <= 4.2 + 1e-9 for r in rows)
    curve = rows[0]["pp_curve"]
    assert [p["accuracy"] for p in curve] == [0.9, 0.95, 0.97, 0.98, 0.99, 1.0]
    assert curve == pp.curve(rows[0]["md5"], rows[0]["mods"], "stable")


def test_skills_in_focus_pull_their_maps_forward(sources):
    table, pool, pp = sources
    level = Level(stars=5.0, measured=True, lowest=3.5, highest=5.5)
    plain = candidates(table, pool, pp, [Wanted("NM", "NM", 1.0, level)], "stable", "fc", [], limit=100)
    speed = candidates(table, pool, pp, [Wanted("NM", "NM", 1.0, level)], "stable", "fc", ["speed"], limit=100)
    assert np.mean([r["s_speed"] for r in speed]) > np.mean([r["s_speed"] for r in plain]) + 0.2
