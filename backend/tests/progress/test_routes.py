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
def test_goals_need_skill_scores(client):
    g = client.get("/api/goals").json()
    assert not g["has_profile"] and g["open"] == [] and g["skills"] == []
    deadline = (dt.date.today() + dt.timedelta(days=7)).isoformat()
    r = client.post("/api/goals", json={"skill": "aim", "target": 60, "deadline": deadline})
    assert r.status_code == 409 and r.json()["code"] == "no_profile"
    assert client.post("/api/goals/plan").status_code == 409


def test_plan_add_and_remove_goals(analysed):
    g = analysed.get("/api/goals").json()
    assert g["has_profile"] and g["skills"]
    if not g["suggested"]:
        pytest.skip("no scored skills in the sample replays")
    g = analysed.post("/api/goals/plan").json()
    assert len(g["open"]) == len(g["suggested"])
    for goal in g["open"]:
        assert goal["state"] in ("on track", "behind", "done", "no data") and goal["days_left"] == 28
        assert goal["current"] is not None and goal["target"] > goal["start"]
    saved = load_settings(workspace(analysed).cache_dir)["goals"]
    assert all({"id", "skill", "start", "target", "created", "deadline", "done"} <= set(x) for x in saved)
    assert len(g["history"]) == len(g["open"]) and g["history"][0]["target"][-1]["score"] == g["open"][0]["target"]
    again = analysed.post("/api/goals/plan").json()  # no second goal for a skill that has one
    assert len(again["open"]) == len(g["open"])
    removed = analysed.delete(f"/api/goals/{g['open'][0]['id']}").json()
    assert len(removed["open"]) == len(g["open"]) - 1
    assert analysed.delete("/api/goals/nope").status_code == 404


def test_add_a_goal(analysed):
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
                }
            ],
        },
        ws.cache_dir,
    )
    g = analysed.get("/api/goals").json()
    assert g["open"] == [] and g["done"][0]["id"] == "g1" and g["done"][0]["state"] == "done"
    assert load_settings(ws.cache_dir)["goals"][0]["done"] == dt.date.today().isoformat()
