import hashlib
import shutil

from osu_coach.library import repository as libmod
from osu_coach.library.repository import Library
from osu_coach.replays import detect
from osu_coach.replays.osr import parse_header, parse_replay_file
from tests.conftest import replay_and_map

NAME = "circlecore__low_frametime_old__replay-osu_24722_433541214.osr"
NAME2 = "circlecore__legit__legit-12.osr"


def test_parse_header_matches_full_parse():
    rp, _, _ = replay_and_map(NAME)
    h = parse_header(open(rp, "rb").read())
    r = parse_replay_file(rp)
    assert (h["beatmap_md5"], h["player"], h["mods"], h["n300"], h["nmiss"], h["score"]) == \
           (r.beatmap_md5, r.player, r.mods, r.n300, r.nmiss, r.score)
    assert h["timestamp"] == r.timestamp.isoformat()
    assert parse_header(b"not a replay" * 10) is None


def test_finds_stable_install_with_custom_songs_folder(tmp_path):
    rp, mp, _ = replay_and_map(NAME)
    root = tmp_path / "osu!"
    (root / "Data" / "r").mkdir(parents=True)
    song_dir = root / "MySongs" / "123 Artist - Title"
    song_dir.mkdir(parents=True)
    (root / "osu!.tester.cfg").write_text("Volume = 50\nBeatmapDirectory = MySongs\n")
    shutil.copy(rp, root / "Data" / "r" / "a-123.osr")
    shutil.copy(mp, song_dir / "map.osu")
    installs = detect.find_installs(stable_roots=[root], lazer_roots=[])
    assert [i.kind for i in installs] == ["stable"]
    assert installs[0].songs == root / "MySongs"
    lib = Library(tmp_path / "cache")
    lib.add_install(installs[0])
    assert len(lib.replays) == 1
    assert lib.replays[0]["beatmap_md5"] in lib.maps


def _store(files_dir, data: bytes):
    h = hashlib.sha256(data).hexdigest()
    p = files_dir / h[0] / h[:2] / h
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def test_finds_replays_and_maps_in_lazer_file_store(tmp_path):
    rp, mp, _ = replay_and_map(NAME)
    root = tmp_path / "lazer"
    (root / "files").mkdir(parents=True)
    (root / "client.realm").write_bytes(b"")
    _store(root / "files", open(rp, "rb").read())
    _store(root / "files", open(mp, "rb").read())
    _store(root / "files", b"\x89PNG not interesting" * 50)
    inst = detect.find_installs(stable_roots=[], lazer_roots=[root])[0]
    assert inst.kind == "lazer"
    lib = Library(tmp_path / "cache")
    lib.add_install(inst)
    assert len(lib.replays) == 1 and lib.replays[0]["source"] == "lazer"
    assert lib.replays[0]["beatmap_md5"] in lib.maps
    # the store is content-addressed -> every file is classified once and cached
    assert len(Library(tmp_path / "cache").index["lazer"]) == 3


def test_eligible_filters_dedupes_and_sorts():
    lib = Library.__new__(Library)
    base = {"beatmap_md5": "a" * 32, "score": 1}
    lib.replays = [
        dict(base, path="1", player="A", mode=0, mods=0, timestamp="2026-01-01T00:00:00"),
        dict(base, path="2", player="A", mode=0, mods=0, timestamp="2026-01-01T00:00:00"),  # same play twice
        dict(base, path="3", player="A", mode=0, mods=128, timestamp="2026-02-01T00:00:00"),  # relax
        dict(base, path="4", player="A", mode=1, mods=0, timestamp="2026-03-01T00:00:00"),    # taiko
        dict(base, path="5", player="B", mode=0, mods=0, timestamp="2026-04-01T00:00:00"),
        dict(base, path="6", player="A", mode=0, mods=8, timestamp="2026-05-01T00:00:00", score=2),
    ]
    assert [r["path"] for r in lib.eligible("A")] == ["6", "1"]
    assert lib.players() == [("A", 2), ("B", 1)]
    assert len(lib.eligible("*")) == 3


def test_analysis_is_cached_by_replay_content(tmp_path, monkeypatch):
    rp, mp, _ = replay_and_map(NAME)
    folder = tmp_path / "plays"
    folder.mkdir()
    shutil.copy(rp, folder / "x.osr")
    shutil.copy(mp, folder / "x.osu")
    lib = Library(tmp_path / "cache")
    lib.add_folder(folder)
    res, errs = lib.analyze(lib.eligible(), workers=1)
    assert not errs and len(res) == 1
    assert res[0].meta["sim_counts"][3] == res[0].meta["nmiss"]

    def boom(*a, **k):
        raise AssertionError("should have been served from cache")
    monkeypatch.setattr(libmod, "_work", boom)
    lib2 = Library(tmp_path / "cache")
    lib2.add_folder(folder)
    res2, errs2 = lib2.analyze(lib2.eligible(), workers=1)
    assert not errs2 and [a.key for a in res2] == [a.key for a in res]


def test_missing_beatmap_is_reported(tmp_path):
    rp, _, _ = replay_and_map(NAME)
    lib = Library(tmp_path / "cache")
    lib.add_files([rp])
    assert lib.missing_maps(lib.eligible()) == [lib.replays[0]["beatmap_md5"]]
    res, errs = lib.analyze(lib.eligible(), workers=1)
    assert res == [] and "beatmap not found" in errs[0][1]


def test_parallel_analysis_matches_sequential(tmp_path):
    folder = tmp_path / "plays"
    folder.mkdir()
    for n in (NAME, NAME2):
        rp, mp, _ = replay_and_map(n)
        shutil.copy(mp, folder / f"{n}.osu")
        for copy in range(2):   # 4 replay files -> big enough batch to use the process pool
            shutil.copy(rp, folder / f"{copy}-{n}")
    seq = Library(tmp_path / "c1")
    seq.add_folder(folder)
    a, _ = seq.analyze(seq.eligible("*"), workers=1)
    par = Library(tmp_path / "c2")
    par.add_folder(folder)
    refs = par.standard_replays()
    assert len(refs) == 4
    b, errs = par.analyze(refs, workers=2)
    assert not errs and len(b) == 4
    assert sorted(x.meta["sim_counts"] for x in a) == sorted({x.key: x.meta["sim_counts"] for x in b}.values())
