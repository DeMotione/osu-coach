"""Getting maps into osu!: collection.db, lazer import folder, stable collection, .osz downloads (routes)."""

import io
import threading
import zipfile
from pathlib import Path

import pytest

from osu_coach.infra.beatmaps import sources
from osu_coach.infra.exports import lazer_import
from osu_coach.infra.exports.collection_db import loads
from osu_coach.infra.map_pool import POOL_PATH
from tests.conftest import wait, workspace

pytestmark = [
    pytest.mark.usefixtures("_isolated"),
    pytest.mark.skipif(not POOL_PATH.exists(), reason="bundled pool not built"),
]


# ------------------------------------------------------------------ exports
@pytest.fixture
def export(client):
    pl = client.get(
        "/api/playlists", params={"skill": "aim", "comfort": 4.0, "ratings": '{"aim":70}', "assessed": "aim"}
    ).json()
    maps = [m for st in pl["stages"] for m in st["maps"]][:6]
    return {
        "name": pl["collection_name"],
        "maps": [{"md5": m["md5"], "beatmapset_id": m["beatmapset_id"]} for m in maps],
    }


def test_export_preview(client, export):
    p = client.post("/api/exports/preview", json=export).json()
    assert p["total_sets"] == len({m["beatmapset_id"] for m in export["maps"]}) == p["lazer_sets"]
    assert not p["stable_available"] and p["preferred_client"] == "stable"
    assert p["lazer_folder"].endswith(lazer_import.safe_name(export["name"]))


def test_collection_db_download(client, export):
    r = client.post("/api/exports/collection-db", json=export)
    assert r.status_code == 200 and r.headers["content-disposition"] == 'attachment; filename="collection.db"'
    _, collections = loads(r.content)
    assert collections == [(export["name"], [m["md5"] for m in export["maps"]])]


def test_lazer_zip_download(client, export):
    r = client.post("/api/exports/lazer-zip", json=export)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    disposition = r.headers["content-disposition"]  # the name has a ★: ASCII fallback + UTF-8 name
    assert disposition.startswith("attachment; filename=\"osu-coach Jumps (4,0_).zip\"; filename*=UTF-8''")
    assert "%E2%98%85" in disposition
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    folder = lazer_import.safe_name(export["name"])
    assert sorted(names) == sorted([f"{folder}/osu!.user.cfg", f"{folder}/collection.db"])


def test_lazer_import_folder(client, export, monkeypatch):
    def fake_download(set_id, dest, progress=None, stop=None):
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        osz = dest / f"{set_id}.osz"
        with zipfile.ZipFile(osz, "w") as z:
            z.writestr("map.osu", "osu file format v14\n")
        return osz

    monkeypatch.setattr(sources, "download_osz", fake_download)
    r = client.post("/api/exports/lazer-pack", json=export)
    assert r.status_code == 202
    job = wait(client, r.json())
    assert job["status"] == "succeeded", job
    res = job["result"]
    folder = Path(res["path"])
    assert (folder / "collection.db").is_file() and (folder / "osu!.user.cfg").is_file()
    assert sorted(res["maps"]) == sorted({m["beatmapset_id"] for m in export["maps"]}) and res["failed"] == []


def test_lazer_import_folder_can_be_cancelled(client, export, monkeypatch):
    first, go = threading.Event(), threading.Event()

    def slow_download(set_id, dest, progress=None, stop=None):
        first.set()
        go.wait(5)
        return None

    monkeypatch.setattr(sources, "download_osz", slow_download)
    job = client.post("/api/exports/lazer-pack", json=export).json()
    assert job["cancellable"] is True
    assert first.wait(5)
    r = client.post(f"/api/jobs/{job['id']}/cancel")
    assert r.status_code == 200 and r.json()["message"] == "Stopping…"
    go.set()
    job = wait(client, job)
    assert job["status"] == "cancelled" and job["result"] is None
    assert not (lazer_import.default_pack_dir(export["name"], workspace(client).cache_dir) / "_downloading").exists()
    assert client.post("/api/exports/lazer-pack", json=export).status_code == 202  # not busy any more


def test_without_lazers_program_the_maps_go_into_the_folder(client, export):
    p = client.post("/api/exports/preview", json=export).json()
    assert p["lazer_auto"] is False  # tests never find the computer's own lazer
    assert Path(p["lazer_folder"]) == workspace(client).cache_dir / "lazer-import" / lazer_import.safe_name(
        export["name"]
    )


def test_with_lazer_the_maps_go_straight_in_and_the_folder_holds_the_collection(client, export, monkeypatch, tmp_path):
    exe = tmp_path / "osulazer" / "current" / "osu!.exe"
    monkeypatch.setattr(lazer_import, "find_lazer", lambda candidates=None: exe)
    handed = []

    def lazer(program, files):  # lazer imports each .osz and deletes it
        handed.append((program, [f.name for f in files]))
        for f in files:
            f.unlink()

    def fake_download(set_id, dest, progress=None, stop=None):
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        osz = dest / f"{set_id} Artist - Title.osz"
        with zipfile.ZipFile(osz, "w") as z:
            z.writestr("map.osu", "osu file format v14\n")
        return osz

    monkeypatch.setattr(lazer_import, "launch", lazer)
    monkeypatch.setattr(sources, "download_osz", fake_download)
    assert client.post("/api/exports/preview", json=export).json()["lazer_auto"] is True
    job = wait(client, client.post("/api/exports/lazer-pack", json=export).json())
    assert job["status"] == "succeeded", job
    res = job["result"]
    sets = sorted({m["beatmapset_id"] for m in export["maps"]})
    assert res["sent_to_lazer"] and sorted(res["imported"]) == sets and res["not_imported"] == []
    assert len(handed) == 1 and handed[0][0] == exe and len(handed[0][1]) == len(sets)
    cache = workspace(client).cache_dir
    folder = Path(res["path"])
    assert folder == cache / "lazer-import" / lazer_import.safe_name(export["name"])
    assert (folder / "collection.db").is_file() and not any((folder / "Songs").iterdir())  # no maps in it
    assert not list((cache / "lazer-maps").glob("*.osz"))  # lazer took them all
    assert not (tmp_path / "home" / "Downloads").exists()

    r = client.post("/api/exports/lazer-pack/delete", json={"name": export["name"]})
    assert r.status_code == 200 and r.json() == {"path": str(folder), "removed": True} and not folder.exists()
    assert client.post("/api/exports/lazer-pack/delete", json={"name": export["name"]}).json()["removed"] is False


def test_cancelling_an_unknown_job(client):
    r = client.post("/api/jobs/nope/cancel")
    assert r.status_code == 404 and r.json()["code"] == "job_not_found"


def test_stable_collection_needs_a_stable_install(client, export):
    r = client.post("/api/exports/stable-collection", json=export)
    assert r.status_code == 404 and r.json()["code"] == "no_stable_install"


def test_stable_collection_is_merged_with_a_backup(client, export, tmp_path, monkeypatch):
    from osu_coach.infra.replays import detect

    root = tmp_path / "osu!"
    (root / "Songs").mkdir(parents=True)
    (root / "osu!.tester.cfg").write_text("")
    from osu_coach.infra.exports.collection_db import read_collection_db, write_collection_db

    write_collection_db(root / "collection.db", {"mine": ["a" * 32]})
    ws = workspace(client)
    monkeypatch.setattr(ws, "installs", lambda refresh=False: detect.find_installs(stable_roots=[root], lazer_roots=[]))
    monkeypatch.setattr(detect, "is_osu_running", lambda: False)
    r = client.post("/api/exports/stable-collection", json=export)
    assert r.status_code == 200, r.text
    assert r.json()["backup"] and Path(r.json()["backup"]).is_file()
    names = [n for n, _ in read_collection_db(root / "collection.db")[1]]
    assert names == ["mine", export["name"]]
    monkeypatch.setattr(detect, "is_osu_running", lambda: True)
    r = client.post("/api/exports/stable-collection", json=export)
    assert r.status_code == 409 and r.json()["code"] == "osu_running"


def test_osz_downloads_report_what_failed(client, tmp_path):
    r = client.post("/api/exports/osz", json={"folder": str(tmp_path / "maps"), "set_ids": [1, 2, 2]})
    job = wait(client, r.json())
    assert job["status"] == "succeeded" and job["result"]["downloaded"] == 0 and job["result"]["failed"] == [1, 2]


def _without_set(export):
    # the second map with no known set, as an old .osu file reads
    maps = [dict(m) for m in export["maps"]]
    maps[1]["beatmapset_id"] = 0
    return {**export, "maps": maps}, maps[1]["md5"]


def test_a_map_without_a_known_set_doesnt_break_the_export(client, export):
    body, _ = _without_set(export)
    p = client.post("/api/exports/preview", json=body)
    assert p.status_code == 200, p.text
    p = p.json()
    assert p["total_sets"] == len({m["beatmapset_id"] for m in body["maps"] if m["beatmapset_id"] > 0}) + 1
    assert p["lazer_sets"] == p["total_sets"] and p["lazer_approximate"]
    r = client.post("/api/exports/collection-db", json=body)
    assert r.status_code == 200 and loads(r.content)[1][0][1] == [m["md5"] for m in body["maps"]]


def test_the_lazer_folder_looks_up_a_maps_unknown_set(client, export, monkeypatch):
    body, md5 = _without_set(export)
    looked_up = []

    def lookup(m):
        looked_up.append(m)
        return {"id": 999, "beatmapset_id": 4242}

    def fake_download(set_id, dest, progress=None, stop=None):
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        osz = dest / f"{set_id}.osz"
        with zipfile.ZipFile(osz, "w") as z:
            z.writestr("map.osu", "osu file format v14\n")
        return osz

    monkeypatch.setattr(sources, "lookup_md5", lookup)
    monkeypatch.setattr(sources, "download_osz", fake_download)
    job = wait(client, client.post("/api/exports/lazer-pack", json=body).json())
    assert job["status"] == "succeeded", job
    assert looked_up == [md5]
    assert 4242 in job["result"]["maps"] and 0 not in job["result"]["maps"] and job["result"]["not_found"] == 0

    monkeypatch.setattr(sources, "lookup_md5", lambda m: None)
    job = wait(client, client.post("/api/exports/lazer-pack", json=body).json())
    assert job["status"] == "succeeded" and job["result"]["not_found"] == 1 and 0 not in job["result"]["maps"]


def test_osz_downloads_skip_unknown_sets(client, tmp_path):
    r = client.post("/api/exports/osz", json={"folder": str(tmp_path / "maps"), "set_ids": [0, -1]})
    assert r.status_code == 422 and r.json()["code"] == "no_sets"
    assert not (tmp_path / "maps").exists()


def test_export_requests_are_validated(client):
    assert client.post("/api/exports/preview", json={"name": "x", "maps": []}).status_code == 422
    bad = {"name": "x", "maps": [{"md5": "zz", "beatmapset_id": 1}]}
    assert client.post("/api/exports/collection-db", json=bad).status_code == 422
