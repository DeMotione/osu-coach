import numpy as np
import pytest

from osu_coach.beatmaps.domain import PlayableBeatmap
from osu_coach.beatmaps.parser import parse_beatmap_file
from osu_coach.analysis.judge import simulate
from osu_coach.replays.osr import parse_replay_file
from tests.conftest import replay_and_map

EXACT_CASES = [
    "osrparse__resources__replay.osr",            # Cookiezi FREEDOM DiVE, NM
    "osrparse__resources__replay2.osr",           # HDHR
    "circlecore__legit__legit-12.osr",            # NF, 303 misses (struggling player)
    "circlecore__auto__auto-3.osr",               # perfect play
]
STABLE_CASES = EXACT_CASES + [
    "circlecore__low_frametime_old__replay-osu_24722_433541214.osr",  # 2015 replay, 49 misses
    "circlecore__legit__legit_snaps-22.osr",      # HDDT
]


def run(name):
    rp, mp, entry = replay_and_map(name)
    replay = parse_replay_file(rp)
    bm = parse_beatmap_file(mp)
    pb = PlayableBeatmap(bm, replay.mods)
    return replay, pb, simulate(pb, replay), entry


@pytest.mark.parametrize("name", EXACT_CASES)
def test_simulated_judgements_match_replay_header_exactly(name):
    replay, _, sim, _ = run(name)
    got = (sim.counts[300], sim.counts[100], sim.counts[50], sim.counts[0])
    want = (replay.n300, replay.n100, replay.n50, replay.nmiss)
    assert got == want


@pytest.mark.parametrize("name", STABLE_CASES)
def test_simulation_is_within_a_few_judgements_of_header(name):
    """Remaining differences are +-1 ms window-edge cases (stable rounds
    fractional audio time); misses must match exactly."""
    replay, _, sim, _ = run(name)
    got = (sim.counts[300], sim.counts[100], sim.counts[50], sim.counts[0])
    want = (replay.n300, replay.n100, replay.n50, replay.nmiss)
    assert got[3] == want[3]
    assert sum(abs(a - b) for a, b in zip(got, want)) <= 6


@pytest.mark.parametrize("name", EXACT_CASES)
def test_simulated_max_combo_matches_header(name):
    replay, _, sim, _ = run(name)
    assert sim.max_combo == replay.max_combo


def test_perfect_play_hit_errors_stay_inside_300_window():
    _, pb, sim, _ = run("circlecore__auto__auto-3.osr")
    errs = np.array([o.hit_error for o in sim.objects if o.hit_error is not None])
    assert len(errs) > 300
    assert np.abs(errs).max() < pb.hit300
    assert abs(errs.mean()) < 10


def test_lazer_replay_uses_lazer_hit_policy():
    replay, pb, sim, _ = run("osrparse__resources__lazer_standard_format.osr")
    assert sim.rules == "lazer"
    stable = simulate(pb, replay, rules="stable")
    # stable notelock cascades would inflate head misses on a lazer play
    lazer_head_misses = sum(1 for o in sim.objects if o.kind != "spinner" and not o.head_hit)
    stable_head_misses = sum(1 for o in stable.objects if o.kind != "spinner" and not o.head_hit)
    assert lazer_head_misses < stable_head_misses
    assert abs(sim.counts[0] - replay.nmiss) <= 0.3 * replay.nmiss


def test_every_miss_gets_a_reason():
    _, _, sim, _ = run("circlecore__legit__legit-12.osr")
    missed_heads = [o for o in sim.objects if o.kind != "spinner" and not o.head_hit]
    assert len(missed_heads) > 100
    reasons = {o.miss_reason for o in missed_heads}
    assert None not in reasons
    assert reasons <= {"aim", "early", "late", "notelock", "no_tap", "lost"}


def test_presses_are_recorded_with_keys_and_durations():
    _, _, sim, _ = run("osrparse__resources__replay.osr")
    keys = {p.key for p in sim.presses}
    assert keys <= {"K1", "K2", "M1", "M2"}
    hit_presses = [p for p in sim.presses if p.target is not None]
    assert len(hit_presses) >= 1900
    durs = [p.duration for p in sim.presses if p.duration is not None]
    assert 10 < np.median(durs) < 200


def test_moving_cursor_away_turns_hits_into_aim_misses():
    replay, pb, base, _ = run("circlecore__auto__auto-3.osr")
    target = next(o for o in base.objects if o.kind == "circle" and o.index > 20)
    t0 = target.time
    win = (replay.t > t0 - pb.hit50 - 50) & (replay.t < t0 + pb.hit50 + 50)
    replay.x = np.where(win, np.clip(replay.x + 3 * pb.radius, 0, 512), replay.x)
    sim = simulate(pb, replay)
    res = sim.objects[target.index]
    assert res.result == 0
    assert res.miss_reason in ("aim", "lost")


def test_removing_a_tap_gives_no_tap_miss():
    replay, pb, base, _ = run("circlecore__auto__auto-3.osr")
    target = next(o for o in base.objects if o.kind == "circle" and o.index > 20)
    win = (replay.t >= target.time - pb.hit50) & (replay.t <= target.time + pb.hit50)
    replay.keys = np.where(win, 0, replay.keys)
    sim = simulate(pb, replay)
    res = sim.objects[target.index]
    assert res.result == 0
    assert res.miss_reason == "no_tap"
