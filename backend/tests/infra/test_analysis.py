import numpy as np
import pandas as pd
import pytest

from osu_coach.domain.analysis.models import along_cross
from osu_coach.infra.library import analyze_files
from tests.conftest import notes_frame, replay_and_map


@pytest.fixture(scope="module")
def struggling():
    rp, mp, _ = replay_and_map("circlecore__legit__legit-12.osr")
    return analyze_files(rp, mp)


def test_object_table_has_one_row_per_object(struggling):
    a = struggling
    assert len(a.notes) == a.meta.n_objects
    assert a.meta.sim_counts[3] == 303  # (300, 100, 50, miss)
    assert a.meta.sim_match is True


def test_every_missed_head_has_reason(struggling):
    o = notes_frame(struggling)
    missed = o[(o["kind"] != "spinner") & (~o["head_hit"]) & (o["result"] >= 0)]
    assert missed["miss_reason"].notna().all()


def test_unstable_rate_is_ten_times_std_of_real_time_errors(struggling):
    o = notes_frame(struggling)
    errs = o.loc[o["head_hit"], "err_real"].dropna()
    assert struggling.meta.ur == pytest.approx(10 * errs.std(ddof=0), rel=1e-6)
    assert 50 < struggling.meta.ur < 400


def test_difficulty_attributes_present(struggling):
    m = struggling.meta
    assert m.stars > 3
    assert m.aim > 0 and m.speed > 0


def test_presses_table(struggling):
    p = pd.DataFrame(struggling.presses.to_columns())
    assert {"key", "time", "duration", "target", "outcome", "same_key_gap"} <= set(p.columns)
    assert len(p) > 1000


def test_dt_errors_are_converted_to_real_time():
    rp, mp, _ = replay_and_map("circlecore__legit__legit_snaps-22.osr")
    a = analyze_files(rp, mp)
    o = notes_frame(a).dropna(subset=["hit_error"])
    assert np.allclose(o["err_real"], o["hit_error"] / 1.5)
    assert a.meta.rate == 1.5


def test_replay_without_results_falls_back_to_simulation():
    """Some tools write .osr files with all-zero result counts."""
    from pathlib import Path

    from osu_coach.infra.library import analyze_bytes
    from osu_coach.infra.replays.osr import parse_replay_file

    rp, mp, _ = replay_and_map("circlecore__legit__legit-12.osr")
    replay = parse_replay_file(rp)
    replay.n300 = replay.n100 = replay.n50 = replay.nmiss = 0
    a = analyze_bytes(replay, Path(mp).read_bytes())
    assert a.meta.header_empty and a.meta.sim_match is None
    assert np.isnan(a.meta.sim_agreement)
    assert a.meta.nmiss == 303
    assert 0.5 < a.meta.accuracy < 1.0


def test_along_cross_projection():
    # moving right; click lands 10px right of centre -> overshoot +10, cross 0
    assert along_cross(10, 0, 1, 0) == pytest.approx((10, 0))
    # moving up (dy<0); click lands 5px above -> overshoot +5
    assert along_cross(0, -5, 0, -1) == pytest.approx((5, 0))
    # moving right; click 4px below centre -> cross +4 (clockwise side)
    a, c = along_cross(0, 4, 1, 0)
    assert a == pytest.approx(0) and c == pytest.approx(4)


def test_movement_starts_where_the_previous_circle_was_hit_else_at_its_end():
    from osu_coach.infra.analysis import _along_cross, _movement_start

    obj = pd.DataFrame(
        {
            "prev_idx": [None, 0, 1, 2],
            "kind": ["circle", "slider", "circle", "circle"],
            "head_hit": [True, True, False, True],
            "click_x": [10.0, 50.0, np.nan, 90.0],
            "click_y": [20.0, 60.0, np.nan, 95.0],
            "end_x": [0.0, 70.0, 80.0, 100.0],
            "end_y": [0.0, 75.0, 85.0, 100.0],
            "x": [0.0, 40.0, 80.0, 110.0],
            "y": [0.0, 60.0, 85.0, 100.0],
        }
    )
    sx, sy = _movement_start(obj)
    # first note: no start; after a hit circle: its click; after a slider or a missed circle: their end
    assert np.isnan(sx[0]) and np.isnan(sy[0])
    assert (sx[1], sy[1]) == (10.0, 20.0)
    assert (sx[2], sy[2]) == (70.0, 75.0)
    assert (sx[3], sy[3]) == (80.0, 85.0)
    obj["start_x"], obj["start_y"] = sx, sy
    ex = np.array([1.0, 3.0, np.nan, 0.0])
    ey = np.array([1.0, 4.0, 2.0, 0.0])
    along, cross = _along_cross(ex, ey, obj, radius=2.0)
    assert np.isnan(along[0]) and np.isnan(along[2])  # no start / no error
    a, c = along_cross(3.0, 4.0, 40.0 - 10.0, 60.0 - 20.0)
    assert (along[1], cross[1]) == (a / 2.0, c / 2.0)
    assert (along[3], cross[3]) == tuple(v / 2.0 for v in along_cross(0.0, 0.0, 30.0, 15.0))
