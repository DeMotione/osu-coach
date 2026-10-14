import datetime as dt

from osu_coach.progress.domain import month_of, period_of

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
