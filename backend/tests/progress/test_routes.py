"""Progress by month / week / day and skill goals."""

import datetime as dt

import pytest

from osu_coach.settings.repository import load_settings, save_settings
from tests.conftest import workspace

pytestmark = pytest.mark.usefixtures("_isolated")


def test_nothing_saved_yet(client):
    assert client.get("/api/progress/players").json() == []
    r = client.get("/api/progress")
    assert r.status_code == 404 and r.json()["code"] == "no_history"


def test_progress_by_period(analysed):
    assert analysed.get("/api/progress/players").json() == [{"name": "Mot1one", "plays": 3}]
    m = analysed.get("/api/progress").json()
    assert m["player"] == "Mot1one" and m["period"] == "month"
    assert m["first_day"].startswith("2026-09")
    assert "skill_reference_stars" in m  # null here: three plays are too few for skill ratings
    row = m["rows"][-1]
    assert row["key"] == "2026-09" and row["plays"] == 3 and row["few_plays"]
    assert set(row["skills"]) >= {"aim", "speed", "accuracy"}
    days = analysed.get("/api/progress", params={"period": "day"}).json()["rows"]
    assert sum(r["plays"] for r in days) == 3 and all(len(r["key"]) == 10 for r in days)
    weeks = analysed.get("/api/progress", params={"period": "week"}).json()["rows"]
    assert all("-W" in r["key"] for r in weeks)
    plays = analysed.get("/api/progress/plays", params={"key": "2026-09"}).json()
    assert len(plays) == 3 and {p["result"] for p in plays} <= {"full combo", "passed", "failed"}
    assert "failed" in {p["result"] for p in plays}
    assert [p["played_at"] for p in plays] == sorted((p["played_at"] for p in plays), reverse=True)


def test_progress_range_and_players(analysed):
    none = analysed.get("/api/progress", params={"since": "2020-01-01", "until": "2020-01-31"}).json()
    assert none["rows"] == []
    r = analysed.get("/api/progress", params={"since": "2026-10-01", "until": "2026-09-01"})
    assert r.status_code == 422 and r.json()["code"] == "bad_date_range"
    assert analysed.get("/api/progress", params={"player": "nobody"}).status_code == 404
    assert analysed.get("/api/progress", params={"period": "year"}).status_code == 422


# ------------------------------------------------------------------ goals
def _measured_profile(analysed):
    """Give the small replay fixture measured ratings and one explicitly missing rating."""
    p = workspace(analysed).profile()
    p.skill_ratings = {
        skill: {"score": score, "maps": 12, "reason": "Not enough replay data" if score is None else None}
        for skill, score in {
            "aim": 81,
            "flow_aim": 77,
            "speed": 68,
            "stamina": 88,
            "accuracy": 33,
            "sliders": 83,
            "reading": None,
            "consistency": 34,
        }.items()
    }


def test_goals_need_skill_scores(client):
    g = client.get("/api/goals").json()
    assert not g["has_profile"] and g["open"] == [] and g["skills"] == []
    deadline = (dt.date.today() + dt.timedelta(days=7)).isoformat()
    r = client.post("/api/goals", json={"skill": "aim", "target": 60, "deadline": deadline})
    assert r.status_code == 409 and r.json()["code"] == "no_profile"
    assert client.post("/api/goals/plan").status_code == 409


def test_plan_add_and_remove_goals(analysed):
    assert analysed.post("/api/goals/plan").status_code == 409  # The small fixture has no measured ratings.
    _measured_profile(analysed)
    g = analysed.get("/api/goals").json()
    assert g["has_profile"] and g["skills"]
    overview = analysed.get("/api/profile/overview").json()
    measured = {s["key"]: s["score"] for s in overview["skills"] if s["score"] is not None}
    assert {s["key"]: s["score"] for s in g["skills"]} == measured
    assert [s["skill"] for s in g["suggested"]] == [
        k for k, score in sorted(measured.items(), key=lambda item: item[1]) if score <= 45
    ][:3]
    if not g["suggested"]:
        pytest.skip("no scored skills in the sample replays")
    suggested = g["suggested"]
    g = analysed.post("/api/goals/plan").json()
    assert [goal["skill"] for goal in g["open"]] == [s["skill"] for s in suggested]
    assert all(goal["score_source"] == "experimental" for goal in g["open"])
    assert all(s["skill"] not in {goal["skill"] for goal in g["open"]} for s in g["suggested"])
    for goal in g["open"]:
        assert goal["state"] in ("on track", "behind", "done", "no data") and goal["days_left"] == 28
        assert goal["current"] is not None and goal["target"] > goal["start"]
    saved = load_settings(workspace(analysed).cache_dir)["goals"]
    assert all({"id", "skill", "start", "target", "created", "deadline", "done"} <= set(x) for x in saved)
    # the saved daily scores are on the goals' rating scale (#34), so each goal has its history
    assert [h["goal_id"] for h in g["history"]] == [goal["id"] for goal in g["open"]]
    again = analysed.post("/api/goals/plan").json()  # no second goal for a skill that has one
    assert len(again["open"]) == len(g["open"])
    removed = analysed.delete(f"/api/goals/{g['open'][0]['id']}").json()
    assert len(removed["open"]) == len(g["open"]) - 1
    assert analysed.delete("/api/goals/nope").status_code == 404


def test_add_a_goal(analysed):
    _measured_profile(analysed)
    skill = analysed.get("/api/goals").json()["skills"][0]
    deadline = (dt.date.today() + dt.timedelta(days=14)).isoformat()
    r = analysed.post("/api/goals", json={"skill": skill["key"], "target": 100, "deadline": deadline})
    assert r.status_code == 201
    goal = r.json()["open"][0]
    assert (
        goal["skill"] == skill["key"]
        and goal["target"] == 100
        and goal["start"] == pytest.approx(skill["score"], abs=0.05)
    )
    past = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    r = analysed.post("/api/goals", json={"skill": skill["key"], "target": 90, "deadline": past})
    assert r.status_code == 422 and r.json()["code"] == "deadline_past"
    assert (
        analysed.post("/api/goals", json={"skill": skill["key"], "target": 101, "deadline": deadline}).status_code
        == 422
    )


def test_a_reached_goal_is_marked_done(analysed):
    _measured_profile(analysed)
    skill = analysed.get("/api/goals").json()["skills"][0]
    ws = workspace(analysed)
    save_settings(
        {
            **load_settings(ws.cache_dir),
            "goals": [
                {
                    "id": "g1",
                    "skill": skill["key"],
                    "start": 1.0,
                    "target": 1.0,
                    "created": "2026-01-01",
                    "deadline": "2027-01-01",
                    "done": None,
                    "score_source": "experimental",
                }
            ],
        },
        ws.cache_dir,
    )
    g = analysed.get("/api/goals").json()
    assert g["open"] == [] and g["done"][0]["id"] == "g1" and g["done"][0]["state"] == "done"
    assert load_settings(ws.cache_dir)["goals"][0]["done"] == dt.date.today().isoformat()


def test_old_lower_level_accuracy_goal_is_paused_and_new_goal_uses_new_scale(analysed):
    _measured_profile(analysed)
    ws = workspace(analysed)
    ws.profile().levels["comfort_stars"] = 4.5
    save_settings(
        {
            **load_settings(ws.cache_dir),
            "goals": [
                {
                    "id": "old-acc",
                    "skill": "accuracy",
                    "start": 0.0,
                    "target": 10.0,
                    "created": "2026-01-01",
                    "deadline": "2026-02-01",
                    "done": None,
                    "score_source": "experimental",
                }
            ],
        },
        ws.cache_dir,
    )
    old = analysed.get("/api/goals").json()["open"][0]
    assert old["state"] == "paused" and old["progress"] is None and old["current"] is None
    assert load_settings(ws.cache_dir)["goals"][0]["done"] is None
    deadline = (dt.date.today() + dt.timedelta(days=14)).isoformat()
    response = analysed.post("/api/goals", json={"skill": "accuracy", "target": 60, "deadline": deadline})
    assert response.status_code == 201
    new = next(g for g in response.json()["open"] if g["id"] != "old-acc")
    assert new["state"] != "paused" and new["current"] == 33
    assert next(g for g in load_settings(ws.cache_dir)["goals"] if g["id"] == new["id"])["score_version"] == 2


def test_goals_of_the_previous_rating_scale_are_paused_not_measured(analysed):
    """Goals saved before 0.10 have no ``score_source``: their scores can't be compared with the Overview's (#70)."""
    _measured_profile(analysed)
    ws = workspace(analysed)
    weakest = min(analysed.get("/api/goals").json()["skills"], key=lambda s: s["score"])
    old = {"start": 1.0, "target": 2.0, "created": "2026-10-18", "deadline": "2027-01-01"}
    save_settings(
        {
            **load_settings(ws.cache_dir),
            "goals": [
                {"id": "old-open", "skill": weakest["key"], **old, "done": None},
                {"id": "old-done", "skill": "consistency", **old, "done": "2026-10-19"},
            ],
        },
        ws.cache_dir,
    )
    g = analysed.get("/api/goals").json()
    # an easy target on the old scale is not counted as reached with today's score
    [paused] = g["open"]
    assert paused["id"] == "old-open" and paused["state"] == "paused"
    assert paused["score_source"] == "legacy" and paused["progress"] is None and paused["current"] is None
    assert load_settings(ws.cache_dir)["goals"][0]["done"] is None
    assert g["behind"] == 0
    [done] = g["done"]
    assert done["id"] == "old-done" and done["state"] == "done" and done["current"] is None
    # its skill is free again for a goal on the current scale
    if weakest["score"] <= 45:
        assert weakest["key"] in [s["key"] for s in g["weak_without_goal"]]


def test_one_open_goal_per_skill_with_a_target_above_the_score(analysed):
    _measured_profile(analysed)
    first, second = analysed.get("/api/goals").json()["skills"][:2]
    deadline = (dt.date.today() + dt.timedelta(days=14)).isoformat()
    assert (
        analysed.post("/api/goals", json={"skill": first["key"], "target": 100, "deadline": deadline}).status_code
        == 201
    )
    again = analysed.post("/api/goals", json={"skill": first["key"], "target": 100, "deadline": deadline})
    assert again.status_code == 409 and again.json()["code"] == "goal_exists"
    low = analysed.post(
        "/api/goals", json={"skill": second["key"], "target": max(1, second["score"]), "deadline": deadline}
    )
    assert low.status_code == 422 and low.json()["code"] == "target_reached"
    assert len(analysed.get("/api/goals").json()["open"]) == 1
