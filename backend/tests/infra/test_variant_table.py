"""The variant table's file: made from .osu files, saved, unpacked once, and the bundled one is the pool's."""

import json

import numpy as np
import pytest

from osu_coach.domain.maps.variants import BY_CONFIGURATION, BY_GEOMETRY, MISSING, PATTERN_COLUMNS, RATES
from osu_coach.domain.player.algorithm import MODEL_VERSION
from osu_coach.infra import variant_table
from osu_coach.infra.beatmaps import difficulty
from osu_coach.infra.beatmaps.performance import CALCULATOR_VERSION
from osu_coach.infra.map_pool import load_pool
from osu_coach.infra.variant_table import (
    POOL_VARIANTS_PATH,
    blank_variants,
    load_table,
    map_variants,
    read_table,
    save_table,
)

needs_rosu = pytest.mark.skipif(not difficulty.available(), reason="rosu-pp-py not installed")


def test_the_bundled_table_is_the_bundled_pools():
    # stale after the pool changes: run backend/tools/build_variant_table.py (without it a search with mods has to
    # download and calculate every pool map)
    assert POOL_VARIANTS_PATH.exists()
    with np.load(POOL_VARIANTS_PATH) as archive:
        meta = json.loads(str(archive["meta"]))
        md5 = archive["md5"].tolist()
        found = archive["found"]
    assert md5 == load_pool()["md5"].tolist()
    assert found.all() and meta["differing"] == 0
    assert (meta["model_version"], meta["calculator_version"]) == (MODEL_VERSION, CALCULATOR_VERSION)
    assert tuple(meta["columns"]) == PATTERN_COLUMNS and tuple(meta["rates"]) == RATES


@needs_rosu
def test_a_maps_part_has_every_configuration(resource_table):
    path, raws = resource_table
    part = map_variants(raws[0])
    assert not part["differs"]  # stable's values, and HD's slider factor and evenness, are the stored ones
    for name in BY_CONFIGURATION:
        assert part[name].shape == (2, 2, len(RATES)) and np.isfinite(part[name]).all()
    for name in BY_GEOMETRY:
        assert part[name].shape == (2, len(RATES)) and np.isfinite(part[name]).all()
    stars = part["stars"]
    assert stars[0, 0, -1] > 1.5 * stars[0, 0, 0] and (stars[1] > stars[0]).all()  # DT x2, and HR
    assert (stars[:, 1] != stars[:, 0]).any()  # HD has stars of its own
    # one row of pattern statistics a geometry, unless the patterns change with the rate
    assert [(hr, rate) for hr, rate, _ in part["segments"]][:1] == [(0, 0)]
    assert {hr for hr, _, _ in part["segments"]} == {0, 1}
    assert all(row.shape == (len(PATTERN_COLUMNS),) for _, _, row in part["segments"])


def test_a_file_without_statistics_has_a_blank_part():
    for raw in (b"not a beatmap", b"osu file format v14\n\n[HitObjects]\n256,192,1000,1,0,0:0:0:0:\n"):
        part = map_variants(raw)
        assert part["segments"] == [] and np.isnan(part["stars"]).all()


def _parts(n: int = 3) -> list[dict | None]:
    rng = np.random.default_rng(1)
    parts: list[dict | None] = []
    for i in range(n):
        part = blank_variants()
        for name in BY_CONFIGURATION:
            part[name][:] = np.cumsum(rng.uniform(0.0, 0.03, part[name].shape), axis=-1) + 3 + i
        part["slider_factor"][:] = rng.uniform(0.9, 1.0, part["slider_factor"].shape)
        part["evenness"][:] = rng.uniform(0.2, 0.9, part["evenness"].shape)
        part["stars"][1, 1, 5] = np.nan
        row = rng.uniform(0, 300, len(PATTERN_COLUMNS)).astype(np.float32)
        row[3] = np.nan
        part["segments"] = [(0, 0, row), (1, 0, row * 2), (1, 40, row * 3)]
        parts.append(part)
    parts.append(None)  # a map whose file was not there
    return parts


def test_a_saved_table_reads_back(tmp_path):
    parts = _parts()
    md5 = [f"{i:032x}" for i in range(len(parts))]
    path = save_table(tmp_path / "table.npz", md5, parts, {"maps": len(parts)})
    table = read_table(path)
    assert table.md5 == tuple(md5) and table.found.tolist() == [True, True, True, False]
    assert table.columns == PATTERN_COLUMNS and table.index[md5[2]] == 2
    for name in (*BY_CONFIGURATION, *BY_GEOMETRY):
        stored = getattr(table, name)
        assert stored.dtype == np.uint16 and (stored[3] == MISSING).all()
        exact = np.stack([p[name] for p in parts[:3]])
        back = np.where(stored[:3] == MISSING, np.nan, stored[:3] / table.scales[name])
        assert np.allclose(back, exact, atol=0.5 / table.scales[name] + 1e-6, equal_nan=True), name
    assert table.stars[0, 1, 1, 5] == MISSING
    assert table.segment_keys.tolist() == [k for i in range(3) for k in (i * 256, i * 256 + 128, i * 256 + 128 + 40)]
    assert np.array_equal(table.segment_rows[2], parts[0]["segments"][2][2], equal_nan=True)
    # a few of its maps, in the order asked for
    some = read_table(path, only=[md5[2], md5[0]])
    assert some.md5 == (md5[2], md5[0]) and some.found.all()
    assert np.array_equal(some.stars, table.stars[[2, 0]]) and np.array_equal(some.evenness, table.evenness[[2, 0]])
    assert some.segment_keys.tolist() == [0, 128, 168, 256, 384, 424]
    assert np.array_equal(some.segment_rows, table.segment_rows[[6, 7, 8, 0, 1, 2]], equal_nan=True)
    # how finely a value is stored is the file's
    coarse = read_table(save_table(tmp_path / "coarse.npz", md5, parts, scales={**table.scales, "stars": 100.0}))
    assert coarse.scales["stars"] == 100.0 and coarse.stars[0, 0, 0, 0] == round(
        float(parts[0]["stars"][0, 0, 0]) * 100
    )


def test_the_table_is_unpacked_once_into_the_data_folder(tmp_path, monkeypatch):
    parts = _parts()
    md5 = [f"{i:032x}" for i in range(len(parts))]
    path = save_table(tmp_path / "table.npz", md5, parts)
    whole = read_table(path)
    table = load_table(tmp_path / "cache", path)
    folders = list((tmp_path / "cache" / "recommendations" / "variant-table").iterdir())
    assert len(folders) == 1 and (folders[0] / "stars.npy").exists()
    assert isinstance(table.stars, np.memmap) and table.md5 == whole.md5
    for name in (*BY_CONFIGURATION, *BY_GEOMETRY, "segment_keys", "found"):
        assert np.array_equal(getattr(table, name), getattr(whole, name)), name
    assert np.array_equal(table.segment_rows, whole.segment_rows, equal_nan=True)
    assert load_table(tmp_path / "cache", path) is table  # kept while the file stays the same
    # unpacked files of an earlier table are removed, and a folder that cannot be written does not stop a search
    variant_table._load.cache_clear()
    del table
    other = save_table(tmp_path / "other.npz", md5[:2], parts[:2])
    assert load_table(tmp_path / "cache", other).md5 == tuple(md5[:2])
    assert len(list((tmp_path / "cache" / "recommendations" / "variant-table").iterdir())) <= 2
    variant_table._load.cache_clear()
    (tmp_path / "blocked").write_text("a file where the folder would be")
    in_memory = load_table(tmp_path / "blocked", path)
    assert in_memory.md5 == whole.md5 and not isinstance(in_memory.stars, np.memmap)
    assert load_table(tmp_path / "cache", tmp_path / "missing.npz") is None


def test_a_table_of_other_versions_is_not_used(tmp_path, monkeypatch):
    parts = _parts(1)
    path = save_table(tmp_path / "table.npz", ["0" * 32, "1" * 32], parts)
    monkeypatch.setattr(variant_table, "MODEL_VERSION", MODEL_VERSION + 1)
    assert read_table(path) is None
    assert load_table(tmp_path / "cache", path) is None
