import datetime as dt

from osu_coach.goals import domain as goals


D0 = dt.date(2026, 10, 1)


def test_goal_progress_and_states():
    g = goals.new_goal("aim", 40, 60, D0 + dt.timedelta(days=20), today=D0)
    s = goals.status(g, 50, today=D0 + dt.timedelta(days=10))
    assert s["progress"] == 0.5 and s["left"] == 10 and s["days_left"] == 10 and s["state"] == "on track"
    assert goals.status(g, 42, today=D0 + dt.timedelta(days=15))["state"] == "behind"
    assert goals.status(g, 45, today=D0 + dt.timedelta(days=25))["state"] == "overdue"
    assert goals.status(g, None, today=D0)["state"] == "no data"
    assert goals.status(g, 61, today=D0)["state"] == "done"


def test_goals_are_marked_done_once_reached():
    g = goals.new_goal("aim", 40, 60, D0 + dt.timedelta(days=20), today=D0)
    out, changed = goals.update([g], {"aim": 59}, today=D0)
    assert not changed and out[0]["done"] is None
    out, changed = goals.update(out, {"aim": 60.4}, today=D0 + dt.timedelta(days=3))
    assert changed and out[0]["done"] == "2026-10-04"
    # stays done even if the score drops later
    assert goals.status(out[0], 50)["state"] == "done"


def test_plan_targets_the_weakest_skills():
    plan = goals.suggested_targets({"aim": 70, "speed": 30, "reading": 45, "sliders": None, "flow_aim": 95}, 2)
    assert plan == [("speed", 30.0, 40.0), ("reading", 45.0, 55.0)]
    assert goals.suggested_targets({"flow_aim": 95}, 1) == [("flow_aim", 95.0, 100.0)]
