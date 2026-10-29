import pytest
from tests.conftest import sample_paths, wait, workspace

from osu_coach.play_goals.schemas import PlayGoalRequest
from osu_coach.play_goals.service import evaluate

pytestmark = pytest.mark.usefixtures("_isolated")


def test_options_and_conditional_starter_farming_work_without_profile(client):
    options = client.get("/api/play-goals")
    assert options.status_code == 200, options.text
    assert options.json()["player"] is None
    assert options.json()["coverage_maps"] >= 40
    response = client.post("/api/play-goals", json={"goal": "farm", "online": False})
    assert response.status_code == 202, response.text
    finished = wait(client, response.json())
    assert finished["status"] == "succeeded", finished
    result = finished["result"]
    assert result["status"] == "insufficient_evidence" and result["recommendations"]
    assert all(r["accuracy"] is None and r["pp_label"].startswith("Conditional") for r in result["recommendations"])
    assert client.get("/api/play-goals").json()["last_request"]["goal"] == "farm"


@pytest.mark.parametrize(
    "body",
    [
        {"goal": "fc"},
        {"goal": "fc", "beatmap": "https://wrong.test/b/1"},
        {"goal": "fc", "beatmap": "https://osu.ppy.sh/beatmapsets/2"},
        {"goal": "fc", "beatmap": "1", "replay_path": "/fake.osr"},
        {"goal": "farm", "farm_mods": []},
        {"goal": "mod", "training_mod": "RX"},
        {"goal": "mod", "training_mod": "EZ"},  # EZ maps are not in the shipped pool yet
    ],
)
def test_invalid_goal_requests_use_standard_errors(client, body):
    response = client.post("/api/play-goals", json=body)
    assert response.status_code == 422
    assert set(response.json()) == {"detail", "code"}


def test_fc_replay_uses_target_mods_and_observed_breaks(analysed):
    path = client_path = next(
        r["path"] for r in analysed.get("/api/check/replays").json()["replays"] if r["mods"] == "NM"
    )
    response = analysed.post(
        "/api/play-goals", json={"goal": "fc", "replay_path": path, "client": "lazer", "online": False}
    )
    finished = wait(analysed, response.json())
    assert finished["status"] == "succeeded", finished
    result = finished["result"]
    assert result["player"] == "Mot1one" and result["replay_path"] == client_path
    assert result["target"]["mods"] == "NM" and result["target"]["client"] == "lazer"
    assert any(b["observed"] and b["timestamps"] for b in result["blockers"])
    assert result["accuracy"] is None


def test_arbitrary_target_offline_reports_missing_bytes(client):
    response = client.post(
        "/api/play-goals", json={"goal": "fc", "beatmap": "https://osu.ppy.sh/b/987654321", "online": False}
    )
    job = wait(client, response.json())
    assert job["status"] == "failed" and "not cached" in job["error"]


def test_custom_mod_training_starter_is_not_a_personalized_diagnosis(client):
    response = client.post("/api/play-goals", json={"goal": "mod", "training_mod": "HD", "online": False})
    result = wait(client, response.json())["result"]
    assert result["recommendations"]
    assert all(r["map"]["mods"] == "HD" and r["accuracy"] is None for r in result["recommendations"])


def test_training_mod_accepts_hr_and_combinations(client):
    for mods in ("HR", "HDHR", "HRDT"):
        response = client.post("/api/play-goals", json={"goal": "mod", "training_mod": mods, "online": False})
        result = wait(client, response.json())["result"]
        assert result["recommendations"]
        assert all(r["map"]["mods"] == mods for r in result["recommendations"])


def test_cancelled_evaluation_checks_reporter_before_work(client):
    from osu_coach.jobs.manager import Cancelled, Job, Reporter

    job = Job(kind="play_goal", cancellable=True)
    job.stop.set()
    with pytest.raises(Cancelled):
        evaluate(workspace(client), PlayGoalRequest(goal="farm"), Reporter(job))


def test_replay_paths_are_not_arbitrary_files(client):
    path, _ = sample_paths("mot1one__lazer_nm.osr")
    response = client.post("/api/play-goals", json={"goal": "fc", "replay_path": str(path), "online": False})
    assert response.status_code == 404 and response.json()["code"] == "replay_not_found"


def test_other_players_attempts_never_diagnose_selected_player(analysed):
    path = next(r["path"] for r in analysed.get("/api/check/replays").json()["replays"] if r["mods"] == "NM")
    workspace(analysed).update_settings(player="Another player")
    response = analysed.post(
        "/api/play-goals", json={"goal": "fc", "replay_path": path, "client": "lazer", "online": False}
    )
    job = wait(analysed, response.json())
    assert job["status"] == "succeeded", job
    result = job["result"]
    assert result["player"] == "Another player"
    assert all(not b["observed"] for b in result["blockers"])
    assert any("another player" in w for w in result["warnings"])


def test_goal_inputs_survive_new_workspace(client):
    from tests.conftest import make_client

    response = client.post("/api/play-goals", json={"goal": "mod", "training_mod": "DT", "online": False})
    assert wait(client, response.json())["status"] == "succeeded"
    with make_client(workspace(client).cache_dir) as restarted:
        options = restarted.get("/api/play-goals").json()
        assert options["last_request"]["training_mod"] == "DT"
