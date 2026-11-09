import datetime as dt
from types import SimpleNamespace

from osu_coach.domain.progress.periods import month_of, period_of

UTC = dt.UTC
EEST = dt.timezone(dt.timedelta(hours=3))  # Tallinn in summer


def test_month_follows_the_computers_time_zone():
    late = dt.datetime(2026, 8, 31, 22, 30)  # replay dates are UTC
    assert month_of(late, UTC) == "2026-08"
    assert month_of(late, EEST) == "2026-09"
    assert month_of("2026-08-31T22:30:00", EEST) == "2026-09"


def test_period_keys_for_days_and_weeks():
    assert period_of(dt.datetime(2026, 10, 12, 22, 30), "day", EEST) == "2026-10-13"
    assert period_of(dt.datetime(2026, 10, 12, 12), "week", UTC) == "2026-W42"


def test_a_period_that_cant_be_computed_does_not_stop_the_others(monkeypatch):
    from osu_coach.domain.player import summarize
    from osu_coach.domain.progress import periods
    from tests.conftest import play_of

    plays = [
        summarize(play_of({"key": f"{month}-{i}", "player": "P", "date": f"2026-{month:02d}-0{i + 1}T12:00:00+00:00"}))
        for month in (1, 2)
        for i in range(periods.FEW_PLAYS)
    ]
    profile = SimpleNamespace(
        skill_ratings={},
        tapping=SimpleNamespace(comfort_bpm=170.0, n=10, ur_single=None),
        aim=SimpleNamespace(aim_err_median=None),
    )

    def broken_in_january(group, *args, **kwargs):  # (the plays here have no notes to build a real profile from)
        if any(p.key.startswith("1-") for p in group):
            raise RuntimeError("one bad period")
        return profile

    monkeypatch.setattr(periods, "build_profile_from", broken_in_january)
    out = periods.period_metrics(plays, UTC)
    assert ("stream_bpm", 170.0, 10) in out[periods.metric_key("month", "2026-02")]
    assert periods.metric_key("month", "2026-01") not in out
