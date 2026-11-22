"""The pool's pp table: made from .osu files, saved, read back, and the bundled one is the bundled pool's."""

import numpy as np
import pytest

from osu_coach.domain.play_goals.pool import ACCURACIES, CONFIGS
from osu_coach.infra import pp_table
from osu_coach.infra.beatmaps.performance import calculate
from osu_coach.infra.map_pool import load_pool
from osu_coach.infra.pp_table import CLIENTS, MISSING, load_pp_table, map_pp, read_pp_table, save_pp_table
from tests.conftest import sample_paths


def _raw() -> bytes:
    return sample_paths("mot1one__lazer_nm.osr")[1].read_bytes()


def test_the_bundled_table_is_the_bundled_pools():
    # stale after the pool or a new rosu-pp: run backend/tools/build_pp_table.py (Farm PP needs it)
    table = load_pp_table()
    assert table is not None, "made for another calculator"
    assert list(table.md5) == load_pool()["md5"].tolist()
    assert (table.pp != MISSING).all()  # every map, combination, client and accuracy


def test_a_maps_part_is_rosus_fc_scenario():
    raw = _raw()
    part = map_pp(raw)
    assert part.shape == (len(CONFIGS), len(CLIENTS), len(ACCURACIES))
    for c, mods in enumerate(CONFIGS.values()):
        for k, client in enumerate(CLIENTS):
            assert part[c, k, 3] == pytest.approx(calculate(raw, mods, client, ACCURACIES[3]), rel=1e-6)
    assert (np.diff(part, axis=-1) >= 0).all()  # more accuracy, more pp
    assert np.isnan(map_pp(b"not a beatmap")).all()


def test_saved_and_read_back_to_a_quarter_pp(tmp_path):
    part = map_pp(_raw())
    path = save_pp_table(tmp_path / "pp.npz", ["a" * 32, "b" * 32], [part, None])
    table = read_pp_table(path)
    curve = table.curve("a" * 32, "HDDT", "lazer")
    assert [p["accuracy"] for p in curve] == list(ACCURACIES)
    stored = part[list(CONFIGS).index("HDDT"), CLIENTS.index("lazer")]
    assert all(abs(p["pp"] - v) <= 0.125 for p, v in zip(curve, stored, strict=True))
    assert table.curve("b" * 32, "NM", "stable") is None  # its file was not there
    assert table.curve("c" * 32, "NM", "stable") is None and table.curve("a" * 32, "EZ", "stable") is None


def test_a_table_of_another_calculator_is_not_used(tmp_path, monkeypatch):
    path = save_pp_table(tmp_path / "pp.npz", ["a" * 32], [map_pp(_raw())])
    monkeypatch.setattr(pp_table, "CALCULATOR_VERSION", "another")
    assert read_pp_table(path) is None
    assert load_pp_table(tmp_path / "missing.npz") is None
