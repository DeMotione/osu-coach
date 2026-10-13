"""Detailed Map Analysis: one replay on its own."""
from conftest import plays_folder, replay_and_map, scan

from osu_coach import progress
from osu_coach.beatmap import read_metadata


def _title(name):
    return read_metadata(replay_and_map(name)[1])["Title"]


def test_without_replays_says_what_to_do(client):
    lst = client.get("/api/check/replays").json()
    assert lst == {"available": False, "replays": [], "selected": None, "focus_md5": None, "only_map": False}


def test_shows_the_newest_replay_and_others_on_request(tmp_path, client):
    scan(client, plays_folder(tmp_path))
    lst = client.get("/api/check/replays").json()
    assert lst["available"] and len(lst["replays"]) == 3
    assert _title("mot1one__lazer_failed.osr") in lst["replays"][0]["map"]            # played last
    assert lst["selected"] == lst["replays"][0]["path"] and not lst["only_map"]
    report = client.post("/api/check/report", json={"path": lst["selected"], "online": False})
    assert report.status_code == 200, report.text
    r = report.json()
    s = r["summary"]
    assert _title("mot1one__lazer_failed.osr") in s["map"] and not s["completed"]
    assert any(v.startswith("Failed") for v in s["verdict"])
    for key in ("bpm", "ur", "ar", "od", "cs", "hp", "length_s"):
        assert s[key] is not None, key
    assert r["map_plays"]["rows"] and r["map_plays"]["rows"][0]["this"] in (True, False)
    oldest = lst["replays"][-1]["path"]
    other = client.post("/api/check/report", json={"path": oldest, "online": False}).json()
    assert _title("mot1one__lazer_nm.osr") in other["summary"]["map"]
    assert other["summary"]["misses"] == 2 and len([e for e in other["events"] if e["what"] == "miss"]) == 2
    assert all(len(e["timestamp"]) == 9 for e in other["events"])                       # mm:ss:mmm
    assert other["timing"] and len(other["timing"]["time"]) == len(other["timing"]["error"])
    assert other["clicks_screen"]["view"] == "screen"


def test_opens_the_replay_chosen_elsewhere_with_its_maps_plays(tmp_path, client):
    folder = plays_folder(tmp_path)
    scan(client, folder)
    path = str(folder / "mot1one__lazer_dthd_spinner.osr")
    lst = client.get("/api/check/replays", params={"path": path, "only_map": True}).json()
    assert lst["selected"] == path and lst["only_map"]
    assert len(lst["replays"]) == 1 and _title("mot1one__lazer_dthd_spinner.osr") in lst["replays"][0]["map"]


def test_a_dropped_replay_is_checked_and_saved_in_the_history(tmp_path, client):
    rp, mp = replay_and_map("mot1one__lazer_nm.osr")
    ups = client.post("/api/uploads", files=[("files", (rp.name, rp.read_bytes())),
                                             ("files", (mp.name, mp.read_bytes()))]).json()
    replay = next(u for u in ups if u["kind"] == "replay")
    beatmap = next(u for u in ups if u["kind"] == "beatmap")
    lst = client.get("/api/check/replays", params={"path": replay["path"]}).json()
    assert lst["available"] and lst["selected"] == replay["path"]
    # the map isn't in any library: the report finds it once it is added too
    from conftest import workspace
    workspace(client).check_library.add_files([beatmap["path"]])
    r = client.post("/api/check/report", json={"path": replay["path"], "online": False})
    assert r.status_code == 200, r.text
    assert _title("mot1one__lazer_nm.osr") in r.json()["summary"]["map"]
    conn = progress.connect(workspace(client).cache_dir)
    try:
        assert progress.players(conn) == [("Mot1one", 1)]
    finally:
        conn.close()


def test_bad_paths(tmp_path, client):
    r = client.post("/api/check/report", json={"path": str(tmp_path / "notes.txt")})
    assert r.status_code == 422 and r.json()["code"] == "not_a_replay"
    r = client.post("/api/check/report", json={"path": str(tmp_path / "gone.osr")})
    assert r.status_code == 404 and r.json()["code"] == "replay_not_found"
    r = client.get("/api/check/replays", params={"path": str(tmp_path / "gone.osr")})
    assert r.status_code == 404


def test_a_replay_without_its_map_offline(tmp_path, client):
    rp, _ = replay_and_map("mot1one__lazer_nm.osr")
    up = client.post("/api/uploads", files=[("files", (rp.name, rp.read_bytes()))]).json()[0]
    r = client.post("/api/check/report", json={"path": up["path"], "online": False})
    assert r.status_code == 422 and r.json()["code"] == "check_failed" and "beatmap" in r.json()["detail"]
