"""Which replays are analysed, and how much each one counts."""

import datetime as dt

import pytest

from osu_coach.domain.player.levels import replay_weight
from osu_coach.domain.replays import scope
from osu_coach.domain.replays.selection import Latest

pytestmark = pytest.mark.usefixtures("_isolated")


def test_you_analyse_your_latest_100_500_or_1000_replays(client):
    # #95: three choices, no "analyse all"
    assert [int(c) for c in Latest] == [100, 500, 1000]
    assert client.get("/api/meta").json()["latest_choices"] == [100, 500, 1000]


def test_only_replays_of_the_last_year_are_analysed(monkeypatch):
    monkeypatch.undo()  # the tests' own setup takes the old sample replays of any year (conftest): the app's window
    assert scope.RECENT_DAYS == 366
    now = dt.datetime(2026, 11, 27, 12, tzinfo=dt.UTC)
    since = scope.recent_start(now)
    assert now - since == dt.timedelta(days=366)
    assert scope.in_window(now - dt.timedelta(days=365), since, None)
    assert not scope.in_window(now - dt.timedelta(days=367), since, None)


def test_a_replay_counts_by_how_close_its_star_rating_is_to_your_level():
    # fully within half a star, then falling off: 1★ away 61%, 1.5★ 14%, 2★ about 1%
    w = replay_weight([6.0, 6.5, 7.0, 7.5, 8.0, 5.0], level=6.5)
    assert w[0] == w[1] == w[2] == 1.0
    assert w[3] == pytest.approx(0.61, abs=0.01)
    assert w[4] == pytest.approx(0.14, abs=0.01)
    assert w[5] == pytest.approx(0.14, abs=0.01)  # easier maps the same as harder ones
    assert replay_weight([9.0], level=6.5)[0] < 0.02
