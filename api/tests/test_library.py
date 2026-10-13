"""Finding replays, choosing which to analyse, analysing them."""
import shutil

from conftest import MOT1ONE, OTHERS, analyse, plays_folder, replay_and_map, scan, wait, workspace

from osu_coach.library import load_settings
from osu_coach_api.errors import Busy


def test_installs_without_osu_on_this_computer(client):
    assert client.get("/api/installs").json() == []


def test_nothing_scanned_yet(client):
    lib = client.get("/api/library").json()
    assert lib == {"scanned": False, "mode": None, "sources": [], "scan_limit": None, "replays": 0, "players": []}
    r = client.get("/api/library/selection")
    assert r.status_code == 409 and r.json()["code"] == "not_scanned"
    assert client.post("/api/analysis", json={}).json()["code"] == "not_scanned"


def test_scan_and_analyse_a_folder(tmp_path, client):
    job = scan(client, plays_folder(tmp_path))
    assert job["kind"] == "scan" and job["result"]["replays"] == 3 and job["result"]["players"] == 1
    lib = client.get("/api/library").json()
    assert lib["scanned"] and lib["mode"] == "library" and lib["players"] == [{"name": "Mot1one", "replays": 3}]
    sel = client.get("/api/library/selection").json()
    assert sel["player"] == "Mot1one" and sel["replays"] == 3 and sel["missing_maps"] == 0 and not sel["files_mode"]
    job = analyse(client)
    assert job["result"] == {"analysed": 3, "skipped": 0, "best_replays": None, "profile_ready": True, "warnings": []}
    status = client.get("/api/analysis").json()
    assert status["analysed"] == 3 and status["player_label"] == "Mot1one" and status["profile_replays"] == 3
    assert load_settings(workspace(client).cache_dir)["player"] == "Mot1one"       # remembered
    summary = client.get("/api/profile/summary").json()
    assert summary["replays"] == 3 and summary["notes"] > 100 and summary["replay_set"] == "all"


def test_scan_remembers_the_choices(tmp_path, client):
    folder = plays_folder(tmp_path)
    scan(client, folder, latest=1000)
    s = client.get("/api/settings").json()
    assert s["latest"] == 1000 and s["folders"] == str(folder) and s["source_mode"] == "library"


def test_scan_follows_the_replay_count_choice(tmp_path, client):
    """A scan of the newest 100 replays, then *All*: the same sources are scanned again, completely."""
    folder = plays_folder(tmp_path, OTHERS)
    job = scan(client, folder, latest=100)
    assert job["result"]["scan_limit"] == 100
    assert client.post("/api/library/rescan", json={"latest": 100}).json()["code"] == "nothing_to_rescan"
    r = client.post("/api/library/rescan", json={"latest": 0})
    assert r.status_code == 202
    job = wait(client, r.json())
    assert job["status"] == "succeeded" and job["result"]["scan_limit"] is None
    assert client.get("/api/library").json()["scan_limit"] is None
    assert load_settings(workspace(client).cache_dir)["latest"] == 0
    analyse(client, player="*", latest=0)
    assert client.get("/api/analysis").json()["player_label"] == "All players"


def test_selection_by_count_and_date(tmp_path, client):
    scan(client, plays_folder(tmp_path))
    newest = client.get("/api/library/selection", params={"latest": 100}).json()
    assert newest["replays"] == 3 and not newest["newest_only"]
    none = client.get("/api/library/selection", params={"date_range": "custom", "date_from": "2020-01-01",
                                                        "date_to": "2020-01-31"}).json()
    assert none["replays"] == 0 and none["empty_range"]
    r = client.get("/api/library/selection", params={"date_range": "custom", "date_from": "2026-10-01",
                                                     "date_to": "2026-09-01"})
    assert r.status_code == 422 and r.json()["code"] == "bad_date_range"
    session = client.get("/api/library/selection", params={"date_range": "session"}).json()
    assert 1 <= session["replays"] <= 3
    r = client.post("/api/analysis", json={"date_range": "custom", "date_from": "2020-01-01", "date_to": "2020-01-31"})
    job = wait(client, r.json())
    assert job["status"] == "failed" and "time range" in job["error"]


def test_unknown_player_falls_back_to_the_one_with_most_replays(tmp_path, client):
    scan(client, plays_folder(tmp_path))
    assert client.get("/api/library/selection", params={"player": "nobody"}).json()["player"] == "Mot1one"


def test_missing_folder_is_a_warning_not_an_error(tmp_path, client):
    job = scan(client, tmp_path / "does-not-exist")
    assert job["result"]["replays"] == 0 and "Folder not found" in job["result"]["warnings"][0]
    r = client.get("/api/library/selection")
    assert r.status_code == 409 and r.json()["code"] == "no_replays"


def test_only_dropped_files(tmp_path, client):
    rp, mp = replay_and_map(MOT1ONE[0])
    r = client.post("/api/uploads", files=[("files", (rp.name, rp.read_bytes())), ("files", ("map.osu", mp.read_bytes()))])
    assert r.status_code == 201, r.text
    ups = r.json()
    assert [u["kind"] for u in ups] == ["replay", "beatmap"]
    r = client.post("/api/library/scan", json={"mode": "files", "files": [u["id"] for u in ups], "latest": 100})
    job = wait(client, r.json())
    assert job["status"] == "succeeded" and job["result"]["replays"] == 1
    assert client.get("/api/library").json()["mode"] == "files"
    sel = client.get("/api/library/selection", params={"latest": 100, "date_range": "7d"}).json()
    assert sel["files_mode"] and sel["replays"] == 1 and sel["date_range"] == "all"     # no count / date filter
    analyse(client)
    assert client.post("/api/library/rescan", json={"latest": 0}).json()["code"] == "nothing_to_rescan"


def test_files_mode_needs_files(client):
    r = client.post("/api/library/scan", json={"mode": "files", "files": []})
    assert r.status_code == 422 and r.json()["code"] == "no_files"
    r = client.post("/api/library/scan", json={"mode": "files", "files": ["never-uploaded.osr"]})
    assert r.status_code == 404 and r.json()["code"] == "upload_not_found"


def test_uploads_only_take_replays_and_maps_and_stay_in_their_folder(client):
    r = client.post("/api/uploads", files=[("files", ("notes.txt", b"hello"))])
    assert r.status_code == 422 and r.json()["code"] == "unsupported_file"
    r = client.post("/api/uploads", files=[("files", ("../../evil.osr", b"x"))])
    up = r.json()[0]
    assert up["id"] == "evil.osr" and "uploads" in up["path"]


def test_a_second_scan_waits_for_the_first(tmp_path, client):
    ws = workspace(client)
    ws.gate.acquire("Analysing replays")
    try:
        r = client.post("/api/library/scan", json={"folders": [str(tmp_path)]})
        assert r.status_code == 409 and r.json()["code"] == "busy" and "Analysing replays" in r.json()["detail"]
    finally:
        ws.gate.release()
    assert isinstance(Busy("x"), Exception)


def test_failed_plays_and_best_replays(tmp_path, client):
    folder = plays_folder(tmp_path, ["mot1one__lazer_failed.osr"])
    shutil.copy(folder / "mot1one__lazer_failed.osr", folder / "copy.osr")
    scan(client, folder)
    client.patch("/api/settings", json={"replay_set": "best"})
    job = analyse(client)
    assert job["result"]["profile_ready"] is False and "Best replays is empty" in job["result"]["warnings"][0]
    status = client.get("/api/analysis").json()
    assert status["best_empty"] and status["profile_replays"] is None
    r = client.get("/api/profile/overview")
    assert r.status_code == 409 and "Best replays" in r.json()["detail"]
    client.patch("/api/settings", json={"replay_set": "all"})
    assert client.get("/api/profile/summary").json()["replays"] == 1      # the copy is the same play
