"""One play's notes as IRT items."""

import numpy as np
import pytest

from osu_coach.domain.player.engines.irt import constants as K
from osu_coach.domain.player.engines.irt.items import group_table, item_table, tapping_time
from osu_coach.infra.library import analyze_files
from tests.conftest import replay_and_map


@pytest.fixture(scope="module")
def stream_play():
    a = analyze_files(*replay_and_map("circlecore__legit__legit-12.osr")[:2])
    return a.notes.played_notes(), a.meta


def test_every_kind_of_item_is_found(stream_play):
    notes, meta = stream_play
    items = item_table(notes, meta)
    assert set(np.unique(items["kind"])) == {K.HEAD, K.SLIDER, K.ACCURACY, K.TIMING}
    for col in ("b_aim", "b_tap", "b_stam", "b_flow", "b_read", "b_sl", "b_acc"):
        assert np.isfinite(items[col]).any(), col
    groups = group_table(notes, meta)
    assert groups.n.sum() == len(items["kind"])
    assert groups.failed().sum() == (items["fail"] >= 0).sum()


def test_a_stream_note_judged_50_fails_its_timing_not_the_note(stream_play):
    notes, meta = stream_play
    items = item_table(notes, meta)
    stream = np.flatnonzero((notes.run_len >= 3) & (notes.run_pos >= 1) & notes.head_hit & (notes.head_result != 50))
    result = notes.head_result.copy()
    result[stream[:20]] = 50
    worse = item_table(notes.replace(head_result=result), meta)
    failed = lambda it, kind: int(((it["kind"] == kind) & (it["fail"] >= 0)).sum())  # noqa: E731
    assert failed(worse, K.TIMING) >= failed(items, K.TIMING) + 15  # a 50 fails the note's timing ...
    assert failed(worse, K.HEAD) == failed(items, K.HEAD)  # ... not the note: it was hit, reading and flow held


def test_tapping_and_stamina_rate_a_tempo_alike(stream_play):
    notes, meta = stream_play
    items = item_table(notes, meta)
    tap, stam = items["b_tap"], items["b_stam"]
    from osu_coach.domain.player.engines.irt.items import tempo_stars

    assert np.nanmax(np.abs(tempo_stars(np.array([200.0, 200.0])) - tempo_stars(np.array([200.0])))) == 0
    assert np.isfinite(tap).any() and np.isfinite(stam).any()


def test_a_stretch_given_up_is_left_out(stream_play):
    notes, meta = stream_play
    from osu_coach.domain.player.engines.irt.items import given_up

    reason = notes.miss_reason.copy()
    hit = notes.head_hit.copy()
    hit[1000:1040], reason[1000:1040] = False, "no_tap"  # 40 notes without input in a row
    idle = notes.replace(head_hit=hit, miss_reason=reason)
    assert given_up(idle)[1000:1040].all() and given_up(idle).sum() >= 40
    assert len(item_table(idle, meta)["kind"]) < len(item_table(notes, meta)["kind"])
    short = notes.replace(head_hit=np.where(np.arange(len(notes)) == 5, False, notes.head_hit))
    assert not given_up(short)[5]  # one miss is no give-up


def test_no_timing_evidence_no_accuracy_items(stream_play):
    notes, meta = stream_play
    assert not (item_table(notes, meta, timing_counts=False)["kind"] == K.ACCURACY).any()


def test_long_dense_tapping_tests_stamina(stream_play):
    notes, _ = stream_play
    elapsed = tapping_time(notes)
    assert elapsed.min() == 0 and elapsed.max() > 0
    gaps = np.nan_to_num(notes.dt_real, nan=np.inf)
    resets = np.flatnonzero(gaps > K.STREAM_GAP_MS)
    assert (elapsed[resets] == 0).all()


def test_more_notes_on_screen_read_harder(stream_play):
    notes, meta = stream_play
    base = item_table(notes, meta)["b_read"]
    crowded = item_table(notes.replace(density=np.asarray(notes.density) * 4), meta)["b_read"]
    heads = np.isfinite(base)
    assert (crowded[heads] >= base[heads]).all() and (crowded[heads] > base[heads]).any()


def test_kick_sliders_are_not_slider_items(stream_play):
    notes, meta = stream_play
    sliders = (notes.kind == "slider") & notes.head_hit
    count = lambda n: int((item_table(n, meta)["kind"] == K.SLIDER).sum())  # noqa: E731
    short = notes.replace(
        slider_len=np.where(sliders, 2 * notes.radius * 0.8, notes.slider_len)
    )  # inside the follow circle
    assert count(notes) > 0 and count(short) == 0


def test_slider_speed_is_held_at_the_top_of_its_scale(stream_play):
    notes, meta = stream_play
    fast = notes.replace(slider_vel_real=np.asarray(notes.slider_vel_real) * 20)
    b = item_table(fast, meta)["b_sl"]
    shape_bonus = K.K_SL * np.log2((1 + 0.5 * 4 + 0.3 * 4 + 0.2 * 4) * 2)
    assert np.nanmax(b) <= 13.0 + shape_bonus + 1e-9
