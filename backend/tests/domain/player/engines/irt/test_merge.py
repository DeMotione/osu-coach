"""Merging the plays: recency, the retry and mapset caps, sessions and the plays left out."""

import datetime as dt

import pytest

from osu_coach.domain.analysis.models import ReplayMeta
from osu_coach.domain.player.engines.irt.merge import late_flags, merge, usable, weights
from tests.domain.player.engines.irt.helpers import simulate

DAY = dt.datetime(2026, 9, 1, 20, 0)


def meta(i=0, md5="m", minutes=0, days=0, **kw):
    when = DAY - dt.timedelta(days=days) + dt.timedelta(minutes=minutes)
    return ReplayMeta(**({"key": f"k{i}", "beatmap_md5": md5, "date": when} | kw))


def test_retries_of_one_setup_count_as_three_plays():
    assert weights([meta(i) for i in range(6)]).sum() == pytest.approx(3.0)


def test_one_mapset_counts_as_five_plays_at_most():
    plays = [meta(i, md5=f"m{i}", beatmapset_id=7) for i in range(10)]
    assert weights(plays).sum() == pytest.approx(5.0)


def test_old_plays_fade():
    w = weights([meta(0), meta(1, md5="b", days=180), meta(2, md5="c", days=270)])
    assert w.tolist() == pytest.approx([1.0, 1.0, 0.5])


def test_plays_late_in_a_session_are_flagged():
    plays = [meta(0, md5="a"), meta(1, md5="b", minutes=15), meta(2, md5="c", minutes=30), meta(3, md5="d", minutes=45)]
    assert late_flags(plays).tolist() == [0, 0, 0, 1]
    apart = [meta(0, md5="a"), meta(1, md5="b", minutes=45)]  # a 45 min gap starts a new session
    assert late_flags(apart).tolist() == [0, 0]


def test_untrusted_simulations_are_left_out():
    assert not usable(meta(sim_agreement=0.9, client="stable"))
    assert not usable(meta(client="lazer", sim_match=False))
    assert usable(meta(sim_agreement=0.99))
    groups = simulate()
    merged = merge([(meta(0), groups), (meta(1, md5="b", sim_agreement=0.5), groups)])
    assert merged.used == 1 and merged.left_out == 1
    assert merged.groups.n.sum() == pytest.approx(groups.n.sum())


def test_sessions_use_when_a_play_started():
    # saved 45 min after the first one, but it took 10 minutes: it started 35 min in, so it isn't late yet
    plays = [
        meta(0, md5="a"),
        meta(1, md5="b", minutes=15),
        meta(2, md5="c", minutes=30),
        meta(3, md5="d", minutes=45, length_s=600.0),
    ]
    assert late_flags(plays).tolist() == [0, 0, 0, 0]
