"""osu!lazer judgement (judge_lazer) against the statistics lazer stores in its own replays."""

import dataclasses
import warnings

import numpy as np
import pytest

from osu_coach.analysis.domain import UnsupportedReplay, playable
from osu_coach.analysis.judge import simulate
from osu_coach.analysis.judge_lazer import lazer_hit_windows, lazer_options, simulate_lazer
from osu_coach.beatmaps.parser import parse_beatmap_bytes, parse_beatmap_file
from osu_coach.library.repository import analyze_bytes
from osu_coach.replays.osr import parse_replay_file
from tests.conftest import replay_and_map

# Nikita's own lazer plays (client 2026.804.2): no mods, DT+HD with a spinner, a failed play
LAZER_CASES = ["mot1one__lazer_nm.osr", "mot1one__lazer_dthd_spinner.osr", "mot1one__lazer_failed.osr"]
STAT_KEYS = (
    "great",
    "ok",
    "meh",
    "miss",
    "large_tick_hit",
    "large_tick_miss",
    "slider_tail_hit",
    "small_tick_hit",
    "small_tick_miss",
    "small_bonus",
    "large_bonus",
    "ignore_hit",
    "ignore_miss",
)


def load(name):
    rp, mp, _ = replay_and_map(name)
    replay = parse_replay_file(rp)
    pb = playable(parse_beatmap_file(mp), replay)
    return replay, pb


@pytest.mark.parametrize("name", LAZER_CASES)
def test_every_stored_statistic_is_reproduced(name):
    replay, pb = load(name)
    sim = simulate_lazer(pb, replay, **lazer_options(replay))
    stored = replay.lazer["statistics"]
    assert {k: sim.lazer_stats[k] for k in STAT_KEYS} == {k: int(stored.get(k, 0)) for k in STAT_KEYS}
    assert sim.max_combo == replay.max_combo
    assert (sim.counts[300], sim.counts[100], sim.counts[50], sim.counts[0]) == (
        replay.n300,
        replay.n100,
        replay.n50,
        replay.nmiss,
    )


def test_simulate_dispatches_lazer_replays_to_lazer_rules():
    replay, pb = load("mot1one__lazer_nm.osr")
    sim = simulate(pb, replay)
    assert sim.rules == "lazer" and sim.lazer_stats is not None
    stable = simulate(pb, replay, rules="stable")
    assert stable.rules == "stable" and stable.lazer_stats is None


def test_options_follow_the_replay():
    replay, _ = load("mot1one__lazer_nm.osr")
    opts = lazer_options(replay)
    assert opts == {
        "classic_slider": False,
        "classic_notelock": False,
        "floored_windows": True,
        "spun_out": False,
        "fail_after": None,
    }
    failed, _ = load("mot1one__lazer_failed.osr")
    st = failed.lazer["statistics"]
    assert lazer_options(failed)["fail_after"] == sum(st.get(k, 0) for k in ("great", "ok", "meh", "miss"))
    # the Classic mod switches on the old slider scoring and note lock
    replay.lazer = dict(replay.lazer, mods=[{"acronym": "CL", "settings": {"classic_note_lock": False}}])
    opts = lazer_options(replay)
    assert opts["classic_slider"] and not opts["classic_notelock"]


def test_hit_windows_are_floored_minus_half_a_millisecond():
    assert lazer_hit_windows(8.7) == (26.5, 69.5, 112.5)
    great, ok, meh = lazer_hit_windows(8.7, floored=False)
    assert great == pytest.approx(27.8, abs=1e-4) and ok == pytest.approx(70.4, abs=1e-4)
    assert meh == pytest.approx(113.0, abs=1e-4)
    assert lazer_hit_windows(5) == (49.5, 99.5, 149.5)
    assert lazer_hit_windows(8) == (31.5, 75.5, 119.5)


def test_classic_slider_scoring_counts_whole_sliders():
    replay, pb = load("mot1one__lazer_nm.osr")
    sim = simulate_lazer(pb, replay, classic_slider=True)
    s = sim.lazer_stats
    objs = pb.beatmap.objects
    n_sliders = sum(o.is_slider for o in objs)
    assert s["great"] + s["ok"] + s["meh"] + s["miss"] == len(objs)  # circles + whole sliders
    assert s["small_tick_hit"] + s["small_tick_miss"] == n_sliders  # tails are small ticks
    assert s["slider_tail_hit"] == 0 and s["ignore_hit"] == 0
    # heads count as large ticks now
    normal = simulate_lazer(pb, replay).lazer_stats
    assert (
        s["large_tick_hit"] + s["large_tick_miss"] == normal["large_tick_hit"] + normal["large_tick_miss"] + n_sliders
    )


TINY_MAP = b"""osu file format v14

[General]
Mode: 0

[Metadata]
Title:tiny
Artist:test
Version:two notes

[Difficulty]
HPDrainRate:5
CircleSize:4
OverallDifficulty:8
ApproachRate:9
SliderMultiplier:1.4
SliderTickRate:1

[TimingPoints]
0,500,4,2,0,100,1,0

[HitObjects]
100,100,1000,1,0,0:0:0:0:
400,300,1080,1,0,0:0:0:0:
"""


def tiny_play(press_at: float):
    """Two far-apart notes 80 ms apart; the cursor waits on the second and taps once."""
    replay, _ = load("mot1one__lazer_nm.osr")
    bm = parse_beatmap_bytes(TINY_MAP)
    t = np.arange(0.0, 1400.0, 10.0)
    t = np.union1d(t, [press_at, press_at + 40])
    keys = np.where((t >= press_at) & (t < press_at + 40), 1 | 4, 0)
    rp = dataclasses.replace(replay, t=t, x=np.full_like(t, 400.0), y=np.full_like(t, 300.0), keys=keys)
    return simulate_lazer(playable(bm, rp), rp)


def test_hitting_a_later_note_misses_the_skipped_one():
    sim = tiny_play(1080)
    first, second = sim.objects
    assert first.result == 0 and first.forced_miss  # lazer's hit policy, not a timeout
    assert second.result == 300
    assert sim.max_combo == 1


def test_a_later_note_cannot_be_hit_before_the_earlier_one_starts():
    sim = tiny_play(990)  # 10 ms before the first note's time
    first, second = sim.objects
    assert second.result == 0 and first.result == 0  # the tap only shook the second note
    assert sim.presses[0].outcome == "notelock"


def test_unsupported_lazer_mods_are_skipped_with_a_reason():
    rp, mp, _ = replay_and_map("mot1one__lazer_nm.osr")
    replay = parse_replay_file(rp)
    replay.lazer = dict(replay.lazer, mods=[{"acronym": "WU"}])
    with pytest.raises(UnsupportedReplay, match="Wind Up"):
        analyze_bytes(replay, mp.read_bytes())


def test_difficulty_adjust_and_mirror_change_the_playable_map():
    replay, _ = load("mot1one__lazer_nm.osr")
    bm = parse_beatmap_file(replay_and_map("mot1one__lazer_nm.osr")[1])
    replay.lazer = dict(
        replay.lazer,
        mods=[
            {"acronym": "DA", "settings": {"circle_size": 7, "approach_rate": 10}},
            {"acronym": "MR", "settings": {"reflection": 1}},
        ],
    )
    pb = playable(bm, replay)
    assert pb.cs == 7 and pb.ar == 10 and pb.od == bm.od
    o = bm.objects[0]
    assert pb.pos(o)[1] == pytest.approx(384 - o.y - pb.stack(o) * pb.radius / 10, abs=1e-6)  # vertical flip


def test_lazer_replays_only_record_left_and_right():
    replay, pb = load("mot1one__lazer_dthd_spinner.osr")
    sim = simulate_lazer(pb, replay)
    assert {p.key for p in sim.presses} <= {"L", "R"}
    hit_objects = [o for o in sim.objects if o.kind != "spinner" and o.head_hit and o.press_id is not None]
    assert len(hit_objects) >= replay.n300 + replay.n100 - 1  # minus the spinner
    assert sum(p.outcome == "hit" for p in sim.presses) == len(hit_objects)


def test_aim_misses_are_not_counted_as_extra_presses():
    replay, pb = load("mot1one__lazer_nm.osr")
    sim = simulate_lazer(pb, replay)
    assert {p.outcome for p in sim.presses} <= {"hit", "none", "off_target", "early_miss", "notelock", "too_early"}
    w_meh = lazer_hit_windows(pb.od)[2]
    starts = np.array([o.time for o in sim.objects if o.kind != "spinner"])
    off = [p for p in sim.presses if p.outcome == "off_target"]
    # an off-target press is a tap in a note's hit window that missed the circle
    assert all(np.abs(starts - p.time).min() <= w_meh for p in off)


def test_sigmoid_does_not_overflow():
    from osu_coach.profile.domain.misses import _sigmoid

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        p = _sigmoid(np.array([-1e5, 0.0, 1e5]))
    assert p[0] < 1e-12 and p[1] == 0.5 and p[2] > 1 - 1e-12
