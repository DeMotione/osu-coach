"""A search with mods from the variant table: the rows the .osu files give, and the playlist they give, without them."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from osu_coach.domain.maps.configuration import SearchOptions
from osu_coach.domain.maps.variants import MISSING, table_rows
from osu_coach.features.maps import service, variant_repository
from osu_coach.features.maps.schemas import PlaylistSearchRequest
from osu_coach.features.maps.variant_repository import variant_rows
from osu_coach.infra.beatmaps import difficulty
from osu_coach.infra.map_pool import load_pool, stats_from_osu
from osu_coach.infra.settings import UserSettings
from osu_coach.infra.variant_table import POOL_VARIANTS_PATH, read_table

pytestmark = pytest.mark.skipif(not difficulty.available(), reason="rosu-pp-py not installed")

ROSU = ("stars", "aim", "speed", "slider_factor", "evenness")


@pytest.mark.parametrize("client", ["lazer", "stable"])
def test_table_rows_are_the_rows_of_the_files(resource_table, tmp_path, client):
    path, raws = resource_table
    table = read_table(path)
    records = [stats_from_osu(raw) for raw in raws]
    options = SearchOptions(allow_hr=True, allow_hd=True, adjustable_dt=True, min_rate=1.10, max_rate=1.30)
    mine = {row["configuration_id"]: row for row in table_rows(table, records, options, client)}
    exact = {}
    for raw, record in zip(raws, records):
        for row in variant_rows(tmp_path, raw, options.configurations(record["md5"], client)):
            exact[row["configuration_id"]] = row
    assert list(mine) == list(exact) and len(mine) == 2 * 88
    for key, theirs in exact.items():
        row = mine[key]
        # every value of a file's row but the speed note count, which nothing reads
        assert set(theirs) - set(row) == {"speed_note_count"} and set(row) <= set(theirs)
        for name, value in theirs.items():
            if name == "speed_note_count":
                continue
            got = row[name]
            if name in ROSU:  # stored rounded
                assert got == pytest.approx(value, abs=0.5 / table.scales[name] + 1e-9), name
            elif name.startswith("s_"):  # from the rounded values
                assert got == pytest.approx(value, abs=0.004), name
            elif isinstance(value, float):
                assert got == pytest.approx(value, rel=2e-6, abs=2e-6), name
            else:
                assert got == value and type(got) is type(value), name


def test_the_bundled_tables_rows_are_the_rows_of_the_files(res, tmp_path):
    # stale after a change to the pattern statistics or a new rosu-pp: run backend/tools/build_variant_table.py
    md5 = "0619c930348063c2a967a3af4d69cd6b"  # a test map that is a pool map
    raw = res(f"maps/{md5}.osu").read_bytes()
    pool = load_pool()
    record = pool[pool["md5"] == md5].to_dict("records")[0]
    table = read_table(POOL_VARIANTS_PATH, only=[md5])
    options = SearchOptions(allow_hr=True, allow_hd=True, adjustable_dt=True, min_rate=1.45, max_rate=1.60)
    mine = list(table_rows(table, [record], options, "lazer"))
    exact = list(variant_rows(tmp_path, raw, options.configurations(md5, "lazer")))
    assert [row["configuration_id"] for row in mine] == [row["configuration_id"] for row in exact]
    assert len(mine) == 4 * 17
    for row, theirs in zip(mine, exact):
        for name, value in theirs.items():
            if name in ROSU:
                assert row[name] == pytest.approx(value, abs=0.5 / table.scales[name] + 1e-9), name
            elif name.startswith("s_"):
                assert row[name] == pytest.approx(value, abs=0.004), name
            elif isinstance(value, float) and name != "speed_note_count":
                assert row[name] == pytest.approx(value, rel=2e-4, abs=2e-4), name  # the pool's own rounding


def test_a_search_reads_the_table_and_no_file(resource_table, tmp_path, monkeypatch):
    path, raws = resource_table
    small = read_table(path)
    records = [stats_from_osu(raw) for raw in raws]
    comfort = round(min(r["stars"] for r in records) + 0.6, 1)
    # the pool: the two maps and, for the reference curves, pool maps around them that the table lists without a file
    bundled = load_pool()
    near = bundled[(bundled["stars"] - comfort).abs() < 1.5]
    near = near[~near["md5"].isin([r["md5"] for r in records])].iloc[::40]
    pool = pd.concat([pd.DataFrame(records), near], ignore_index=True)
    blank = len(near)
    table = replace(
        small,
        md5=(*small.md5, *near["md5"]),
        found=np.concatenate([small.found, np.zeros(blank, dtype=bool)]),
        **{
            name: np.concatenate([getattr(small, name), np.full((blank, *getattr(small, name).shape[1:]), MISSING)])
            for name in ROSU
        },
    )
    maps = tmp_path / "files" / "recommendations" / "maps"
    maps.mkdir(parents=True)
    for raw, record in zip(raws, records):
        (maps / f"{record['md5']}.osu").write_bytes(raw)
    monkeypatch.setattr(variant_repository, "download_osu", lambda *a, **k: None)

    def ws(cache_dir):
        return SimpleNamespace(
            pool=lambda: pool,
            profile=lambda: None,
            settings=lambda: UserSettings(),
            library=None,
            libraries=lambda: [],
            preferred_client=lambda: "lazer",
            plays=[],
            cache_dir=cache_dir,
        )

    request = PlaylistSearchRequest(
        skill="aim",
        comfort=comfort,
        ratings='{"aim":50,"reading":55}',
        assessed="aim,reading",
        min_relevance=0,
        allow_hr=True,
        allow_hd=True,
        adjustable_dt=True,
        min_rate=1.10,
        max_rate=1.30,
    )
    progress = []
    monkeypatch.setattr(service, "load_table", lambda cache_dir: None)
    from_files = service.search(ws(tmp_path / "files"), request, lambda *p: progress.append(p))

    def no_file(*args, **kwargs):
        raise AssertionError("a search from the variant table reads no .osu file")

    monkeypatch.setattr(service, "load_table", lambda cache_dir: table)
    monkeypatch.setattr(service, "verified_bytes", no_file)
    monkeypatch.setattr(service, "_search_map_results", no_file)
    progress.clear()
    from_table = service.search(ws(tmp_path / "table"), request, lambda *p: progress.append(p))

    assert progress[0][:2] == (0, len(pool)) and progress[-1] == (len(pool), len(pool), "Ranking complete")
    assert not (tmp_path / "table").exists()
    assert (from_table.coverage_maps, from_table.unavailable_maps) == (2, blank)
    assert (from_files.coverage_maps, from_files.unavailable_maps) == (2, blank)
    assert from_table.calculator_unavailable_maps == from_table.unavailable_configurations == 0
    assert from_table.maps == from_files.maps > 0
    for mine, theirs in zip(from_table.stages, from_files.stages, strict=True):
        assert (mine.stage, mine.eligible, mine.excluded) == (theirs.stage, theirs.eligible, theirs.excluded)
        assert mine.target_stars == theirs.target_stars
        assert [m.configuration_id for m in mine.maps] == [m.configuration_id for m in theirs.maps]
        for a, b in zip(mine.maps, theirs.maps):
            assert (a.md5, a.mods, a.rate, a.title, a.url, a.beatmap_id) == (
                b.md5,
                b.mods,
                b.rate,
                b.title,
                b.url,
                b.beatmap_id,
            )
            assert a.stars == pytest.approx(b.stars, abs=6e-4)
            assert (a.bpm, a.ar, a.od, a.length_s) == pytest.approx((b.bpm, b.ar, b.od, b.length_s), rel=1e-6)
            assert a.skill_demand == pytest.approx(b.skill_demand, abs=0.05)
            assert a.formula_score == pytest.approx(b.formula_score, abs=0.01)
            assert a.why == b.why


def test_a_table_of_another_pool_is_not_used(resource_table, tmp_path, monkeypatch):
    table = read_table(resource_table[0])
    listed = pd.DataFrame({"md5": list(table.md5)})
    monkeypatch.setattr(service, "load_table", lambda cache_dir: table)
    assert service._pool_table(listed, tmp_path) is table
    assert service._pool_table(pd.DataFrame({"md5": [*table.md5, "f" * 32]}), tmp_path) is None
    monkeypatch.setattr(service, "load_table", lambda cache_dir: None)
    assert service._pool_table(listed, tmp_path) is None
