import numpy as np
import pytest

from osu_coach.analysis.domain import along_cross
from osu_coach.library.repository import analyze_files
from tests.conftest import replay_and_map


@pytest.fixture(scope="module")
def struggling():
    rp, mp, _ = replay_and_map("circlecore__legit__legit-12.osr")
    return analyze_files(rp, mp)


def test_object_table_has_one_row_per_object(struggling):
    a = struggling
    assert len(a.objects) == a.meta["n_objects"]
    assert a.meta["sim_counts"][3] == 303  # (300, 100, 50, miss)
    assert a.meta["sim_match"] is True


def test_every_missed_head_has_reason(struggling):
    o = struggling.objects
    missed = o[(o["kind"] != "spinner") & (~o["head_hit"]) & (o["result"] >= 0)]
    assert missed["miss_reason"].notna().all()


def test_unstable_rate_is_ten_times_std_of_real_time_errors(struggling):
    o = struggling.objects
    errs = o.loc[o["head_hit"], "err_real"].dropna()
    assert struggling.meta["ur"] == pytest.approx(10 * errs.std(ddof=0), rel=1e-6)
    assert 50 < struggling.meta["ur"] < 400


def test_difficulty_attributes_present(struggling):
    m = struggling.meta
    assert m["stars"] > 3
    assert m["aim"] > 0 and m["speed"] > 0


def test_presses_table(struggling):
    p = struggling.presses
    assert {"key", "time", "duration", "target", "outcome", "same_key_gap"} <= set(p.columns)
    assert len(p) > 1000


def test_dt_errors_are_converted_to_real_time():
    rp, mp, _ = replay_and_map("circlecore__legit__legit_snaps-22.osr")
    a = analyze_files(rp, mp)
    o = a.objects.dropna(subset=["hit_error"])
    assert np.allclose(o["err_real"], o["hit_error"] / 1.5)
    assert a.meta["rate"] == 1.5


def test_replay_without_results_falls_back_to_simulation():
    """Some tools write .osr files with all-zero result counts."""
    from pathlib import Path

    from osu_coach.library.repository import analyze_bytes
    from osu_coach.replays.osr import parse_replay_file

    rp, mp, _ = replay_and_map("circlecore__legit__legit-12.osr")
    replay = parse_replay_file(rp)
    replay.n300 = replay.n100 = replay.n50 = replay.nmiss = 0
    a = analyze_bytes(replay, Path(mp).read_bytes())
    assert a.meta["header_empty"] and a.meta["sim_match"] is None
    assert np.isnan(a.meta["sim_agreement"])
    assert a.meta["nmiss"] == 303
    assert 0.5 < a.meta["accuracy"] < 1.0


def test_along_cross_projection():
    # moving right; click lands 10px right of centre -> overshoot +10, cross 0
    assert along_cross(10, 0, 1, 0) == pytest.approx((10, 0))
    # moving up (dy<0); click lands 5px above -> overshoot +5
    assert along_cross(0, -5, 0, -1) == pytest.approx((5, 0))
    # moving right; click 4px below centre -> cross +4 (clockwise side)
    a, c = along_cross(0, 4, 1, 0)
    assert a == pytest.approx(0) and c == pytest.approx(4)
