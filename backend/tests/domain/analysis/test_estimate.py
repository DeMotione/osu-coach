"""How long an analysis takes, worked out before it starts (#95)."""

import pytest

from osu_coach.domain.analysis.estimate import (
    STARTUP,
    Plan,
    analysis_seconds,
    parallel_work,
    replay_seconds,
)


def test_a_bigger_replay_takes_longer_and_lazer_more_per_byte():
    assert replay_seconds(0.06, False) > replay_seconds(0.02, False) > 0
    assert replay_seconds(0.05, True) > replay_seconds(0.05, False)
    assert replay_seconds(0.0, True) > 0  # never free


def test_workers_share_the_work_and_the_speed_scales_it():
    plan = Plan(new=((0.04, False),) * 400 + ((0.06, True),) * 200, from_cache=0, stored=0)
    one, four = analysis_seconds(plan, 1), analysis_seconds(plan, 4)
    assert four < one / 3
    assert analysis_seconds(plan, 4, speed=2.0) - STARTUP == pytest.approx(
        2 * parallel_work(plan, 4) + (four - STARTUP - parallel_work(plan, 4))
    )


def test_replays_analysed_before_cost_next_to_nothing():
    done = Plan(new=(), from_cache=0, stored=1000)
    assert analysis_seconds(done, 4) < 10
    assert analysis_seconds(Plan(new=(), from_cache=1000, stored=0), 4) > analysis_seconds(done, 4)
    assert done.replays == 1000


def test_a_few_replays_are_analysed_in_one_process():
    few = Plan(new=((0.04, False),) * 3, from_cache=0, stored=0)
    assert parallel_work(few, 8) == pytest.approx(3 * replay_seconds(0.04, False))
