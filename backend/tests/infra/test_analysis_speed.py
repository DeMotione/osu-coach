"""How fast this computer analyses, measured by its own analyses (#95)."""

import pytest

from osu_coach.infra import analysis_speed


def test_the_speed_follows_the_analyses(tmp_path):
    assert analysis_speed.speed(tmp_path) == 1.0  # not measured yet
    analysis_speed.record(tmp_path, estimated=100, took=50, analysed=200)
    assert analysis_speed.speed(tmp_path) == pytest.approx(0.75)  # half way to the measurement
    analysis_speed.record(tmp_path, estimated=100, took=50, analysed=200)
    assert analysis_speed.speed(tmp_path) == pytest.approx(0.625)


def test_small_or_odd_analyses_say_nothing(tmp_path):
    analysis_speed.record(tmp_path, estimated=10, took=40, analysed=analysis_speed.ENOUGH - 1)
    analysis_speed.record(tmp_path, estimated=10, took=-3, analysed=500)
    analysis_speed.record(tmp_path, estimated=0, took=3, analysed=500)
    assert analysis_speed.speed(tmp_path) == 1.0
    (tmp_path / analysis_speed.FILE).write_text("not json")
    assert analysis_speed.speed(tmp_path) == 1.0
