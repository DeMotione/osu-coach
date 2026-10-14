"""'Latest N replays': the scan reads the newest replay files first and stops as soon as the newest N
plays are certain; beatmaps are then looked up only for the replays that need them."""
import datetime as dt
import hashlib
import os
import shutil
from pathlib import Path

from osu_coach.cli import main
from osu_coach.library.repository import Library
from osu_coach.replays import locate
from osu_coach.replays.domain import UNSUPPORTED_LAZER_MODS
from osu_coach.replays.eligibility import analysable, skip_reason
from osu_coach.replays.osr import lazer_info, lazer_mod_acronyms, parse_header
from tests.conftest import replay_and_map

MINE = ["mot1one__lazer_nm.osr", "mot1one__lazer_dthd_spinner.osr", "mot1one__lazer_failed.osr"]  # old -> new
OTHERS = ["circlecore__legit__legit-12.osr", "osrparse__resources__replay.osr",
          "circlecore__legit__legit_snaps-22.osr"]
OLD = dt.datetime(2025, 1, 1, tzinfo=dt.UTC).timestamp()


def played(name: str) -> float:
    return locate.play_time(parse_header(replay_and_map(name)[0].read_bytes()))


def _touch(p: Path, t: float) -> Path:
    os.utime(p, (t, t))
    return p


def _store(files_dir: Path, data: bytes, mtime: float) -> Path:
    h = hashlib.sha256(data).hexdigest()
    p = files_dir / h[0] / h[:2] / h
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return _touch(p, mtime)


def _lazer(tmp_path, replay_time) -> locate.Install:
    """A lazer install: replays written when they were played (``replay_time``), maps downloaded long before."""
    root = tmp_path / "lazer"
    (root / "files").mkdir(parents=True)
    (root / "client.realm").write_bytes(b"")
    for i, n in enumerate(MINE + OTHERS):
        rp, mp, _ = replay_and_map(n)
        _store(root / "files", rp.read_bytes(), replay_time(n))
        _store(root / "files", mp.read_bytes(), OLD + i)
    _store(root / "files", b"\x89PNG not interesting" * 50, OLD - 5)
    return locate.find_installs(stable_roots=[], lazer_roots=[root])[0]


def _paths(refs):
    return [r["path"] for r in refs]


# ------------------------------------------------------------------ reading the header
def test_lazer_mods_are_read_without_decoding_the_frames():
    path = replay_and_map("mot1one__lazer_dthd_spinner.osr")[0]
    data = path.read_bytes()
    assert lazer_mod_acronyms(lazer_info(data)) == ["DT", "HD"]
    assert locate.replay_header(path)["lazer_mods"] == ["DT", "HD"]
    assert lazer_info(replay_and_map("osrparse__resources__replay.osr")[0].read_bytes()) is None  # stable replay
    assert lazer_info(data[:300]) is None                                                    # cut short


def test_replay_headers_cached_by_an_older_version_are_read_again():
    index = {"lazer": {"a" * 64: {"k": "osr", "h": {"player": "A"}}, "b" * 64: {"k": "osu", "md5": "m"},
                       "c" * 64: {"k": "x"}},
             "osr": {"r.osr": [1, 2, {"player": "A"}]}, "files": {"m.osu": [1, 2, "m"]}}
    locate.upgrade_index(index)
    assert index == {"lazer": {"b" * 64: {"k": "osu", "md5": "m"}, "c" * 64: {"k": "x"}},
                     "files": {"m.osu": [1, 2, "m"]}, "v": locate.SCAN_VERSION}
    index["osr"] = {"r.osr": [1, 2, {"player": "A"}]}
    locate.upgrade_index(index)  # up to date: kept
    assert "osr" in index


def test_replays_with_mods_the_simulation_cant_follow_are_left_out():
    h = {"mode": 0, "mods": 0, "lazer_mods": ["WU"], "player": "A", "beatmap_md5": "a" * 32, "score": 1,
         "timestamp": "2026-01-01T00:00:00"}
    assert skip_reason(h) == UNSUPPORTED_LAZER_MODS["WU"] and not analysable(h)
    assert analysable(dict(h, lazer_mods=["DT", "HD"])) and analysable(dict(h, lazer_mods=None))
    lib = Library.__new__(Library)
    lib.replays = [dict(h, path="1"), dict(h, path="2", lazer_mods=[], score=2, timestamp="2026-01-02T00:00:00")]
    assert _paths(lib.eligible("A")) == ["2"]
    assert lib.left_out("A") == {UNSUPPORTED_LAZER_MODS["WU"]: 1}
    assert not lib.left_out("A", since="2026-01-02T00:00:00")


# ------------------------------------------------------------------ when to stop
def _h(player, day, hour=12, **kw):
    return dict({"player": player, "mode": 0, "mods": 0, "beatmap_md5": f"{day:032d}", "score": day * 100 + hour,
                 "timestamp": f"2026-09-{day:02d}T{hour:02d}:00:00"}, **kw)


def _t(day, hour=12):
    return locate.play_time(_h("", day, hour))


def test_newest_replays_stops_only_when_no_older_file_can_hold_a_newer_play():
    pick = locate.NewestReplays(2, accept=analysable)
    pick.add(_h("A", 20))
    assert not pick.done(_t(1))            # one play so far
    pick.add(_h("A", 20))                  # the same play again (an exported copy) doesn't count
    pick.add(_h("A", 19, mods=128))        # relax doesn't count
    pick.add(_h("A", 19, lazer_mods=["WU"]))
    assert not pick.done(_t(1))
    pick.add(_h("B", 18))
    pick.add(_h("A", 15))
    assert pick.target() == "A"            # whoever has the most replays: you, on your own computer
    assert pick.done(_t(13))               # a file from 2 days before A's 2nd newest play can't be newer
    assert not pick.done(_t(14, 18))       # within a day: the file time may be off (time zone)
    assert not pick.done(_t(16))
    everybody = locate.NewestReplays(2, player="*")
    b = locate.NewestReplays(2, player="B")
    for h in (_h("A", 20), _h("B", 18), _h("A", 15)):
        everybody.add(h)
        b.add(h)
    assert everybody.done(_t(16)) and not everybody.done(_t(17))
    assert not b.done(_t(1))               # B has a single replay: read on


# ------------------------------------------------------------------ scanning
def test_latest_lazer_scan_reads_only_the_newest_files(tmp_path):
    inst = _lazer(tmp_path, lambda n: played(n) + 60)
    full = Library(tmp_path / "full")
    full.add_install(inst)
    assert len(full.replays) == 6 and not full.has_unread_maps()
    for n in (1, 2, 3):
        lib = Library(tmp_path / f"latest{n}")
        lib.add_install(inst, latest=n)
        assert lib.scan_limit == n
        assert len(lib.replays) == n               # stopped right after the newest n
        mine = lib.eligible("Mot1one", n)
        assert _paths(mine) == _paths(full.eligible("Mot1one", n))
        assert lib.has_unread_maps("lazer")        # the maps are older than the replays: not read yet
        assert lib.missing_maps(mine) == []        # ...looked up when needed
        assert {r["beatmap_md5"] for r in mine} <= lib.installed["lazer"]
        assert len(lib.index["lazer"]) < len(full.index["lazer"])


def test_latest_scan_reads_everything_when_file_times_say_nothing(tmp_path):
    copied = dt.datetime(2026, 10, 1, tzinfo=dt.UTC).timestamp()  # e.g. all copied from a backup
    inst = _lazer(tmp_path, lambda n: copied)
    lib = Library(tmp_path / "cache")
    lib.add_install(inst, latest=1)
    assert len(lib.replays) == 6
    assert _paths(lib.eligible("Mot1one", 1)) == [r["path"] for r in lib.replays
                                                  if r["timestamp"].startswith("2026-09-20")]


def test_latest_stable_scan_hashes_songs_only_when_needed(tmp_path):
    root = tmp_path / "osu!"
    (root / "Data" / "r").mkdir(parents=True)
    (root / "osu!.tester.cfg").write_text("Volume = 50\n")
    for i, n in enumerate(MINE + OTHERS):
        rp, mp, _ = replay_and_map(n)
        _touch(Path(shutil.copy(rp, root / "Data" / "r" / f"{i}.osr")), played(n) + 60)
        song = root / "Songs" / f"{i} Artist - Title"
        song.mkdir(parents=True)
        _touch(Path(shutil.copy(mp, song / "map.osu")), OLD + i)
    inst = locate.find_installs(stable_roots=[root], lazer_roots=[])[0]
    full = Library(tmp_path / "full")
    full.add_install(inst)
    lib = Library(tmp_path / "cache")
    lib.add_install(inst, latest=1)
    assert len(lib.replays) == 1 and not lib.index.get("files")      # Songs untouched so far
    mine = lib.eligible("Mot1one", 1)
    assert _paths(mine) == _paths(full.eligible("Mot1one", 1))
    assert lib.missing_maps(mine) == []
    assert 0 < len(lib.index["files"]) < 6                           # newest .osu files first, then stop


def test_latest_folder_scan(tmp_path):
    folder = tmp_path / "plays"
    folder.mkdir()
    for n in MINE + OTHERS:
        rp, mp, _ = replay_and_map(n)
        _touch(Path(shutil.copy(rp, folder / n)), played(n) + 60)
        shutil.copy(mp, folder / f"{n}.osu")
    lib = Library(tmp_path / "cache")
    lib.add_folder(folder, latest=2)
    assert len(lib.replays) == 2 and lib.missing_maps(lib.replays) == []
    lib = Library(tmp_path / "cache")
    lib.add_folder(folder, latest=2, player="Cookiezi")  # only one replay of Cookiezi: reads on to the end
    assert len(lib.replays) == 6


# ------------------------------------------------------------------ command line and app
def test_cli_latest_reads_and_analyses_only_the_newest(tmp_path, capsys):
    folder = tmp_path / "plays"
    folder.mkdir()
    for n in MINE:
        rp, mp, _ = replay_and_map(n)
        _touch(Path(shutil.copy(rp, folder / n)), played(n) + 60)
        shutil.copy(mp, folder / f"{n}.osu")
    rc = main(["analyze", "--no-auto", "--offline", "--folder", str(folder), "--workers", "1", "-q",
               "--latest", "1", "--cache", str(tmp_path / "cache")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "osu-coach report — Mot1one: 1 newest replays" in out
