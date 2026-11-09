"""The one-click lazer import folder (lazer_import)."""

import io
import zipfile
from pathlib import Path

from osu_coach.cli import main
from osu_coach.domain.exports.downloads import sets_to_download
from osu_coach.infra.exports import lazer_import
from osu_coach.infra.exports.collection_db import loads, read_collection_db

MD5S = ["0" * 32, "1" * 32]


def fake_osz(tmp_path: Path, sid: int, evil: bool = False) -> Path:
    p = tmp_path / f"{sid} Artist - Title.osz"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("Artist - Title (mapper) [Easy].osu", "osu file format v14\n")
        z.writestr("audio.mp3", b"ID3")
        z.writestr("sb/bg.png", b"\x89PNG")
        if evil:
            z.writestr("../../escaped.txt", "nope")
    return p


def test_pack_looks_like_a_stable_install_with_maps_and_collection(tmp_path):
    calls = []

    def download(sid, folder):
        calls.append(sid)
        folder.mkdir(parents=True, exist_ok=True)
        return None if sid == 3 else fake_osz(folder, sid, evil=(sid == 2))

    dest = tmp_path / "pack"
    res = lazer_import.build_pack(dest, {"osu-coach: Aim (2.5★)": MD5S}, [1, 2, 2, 3], download=download)
    assert res["path"] == dest and res["maps"] == [1, 2] and res["failed"] == [3]
    assert sorted(calls) == [1, 2, 3]
    assert (dest / "osu!.user.cfg").read_bytes() == b""  # lazer: "osu!.*.cfg" marks a stable install
    assert read_collection_db(dest / "collection.db")[1] == [("osu-coach: Aim (2.5★)", MD5S)]
    assert (dest / "Songs" / "1" / "Artist - Title (mapper) [Easy].osu").exists()
    assert (dest / "Songs" / "2" / "sb" / "bg.png").exists()
    assert not (tmp_path / "escaped.txt").exists() and not (dest / "escaped.txt").exists()
    assert not (dest / "_downloading").exists()  # .osz files are removed after unpacking
    # a second run keeps the unpacked sets instead of downloading them again
    calls.clear()
    res = lazer_import.build_pack(dest, {"x": MD5S}, [1, 2], download=download)
    assert calls == [] and res["maps"] == [1, 2]


def test_folder_names_have_no_dots_or_forbidden_characters():
    name = lazer_import.safe_name('osu-coach: Aim (2.5★) <a/b\\c|d?e*"f>')
    assert "." not in name and not set(name) & set('\\/:*?"<>|')
    assert name.startswith("osu-coach Aim (2,5★)")
    assert lazer_import.safe_name(":::") == "osu-coach playlist"
    assert lazer_import.default_pack_dir("osu-coach: Aim (2.5★)").name == "osu-coach Aim (2,5★)"


def test_the_folder_is_in_the_data_folder_not_downloads(tmp_path):
    dest = lazer_import.default_pack_dir("osu-coach: Aim (2.5★)", tmp_path)
    assert dest == tmp_path / "lazer-import" / "osu-coach Aim (2,5★)"


def test_only_folders_osu_coach_made_are_removed(tmp_path, monkeypatch):
    base = tmp_path / "lazer-import"
    old, new, other = base / "old", base / "new", base / "mine"
    for f in (old, new):
        lazer_import.build_pack(f, {"x": MD5S})
    other.mkdir()
    (other / "keep.txt").write_text("not ours")
    monkeypatch.setattr(lazer_import.clock, "timestamp", lambda: (old / "osu!.user.cfg").stat().st_mtime + 2 * 86400)
    assert lazer_import.remove_old_packs(base, keep=new) == [old]
    assert not old.exists() and new.exists() and other.exists()
    assert not lazer_import.remove_pack(other) and other.exists()
    lazer_import.build_pack(base / "osu-coach Aim (2,5★)", {"x": MD5S})
    assert lazer_import.find_pack("osu-coach: Aim (2.5★)", tmp_path) == base / "osu-coach Aim (2,5★)"
    assert lazer_import.find_pack("../../mine", tmp_path) is None and lazer_import.find_pack("mine", tmp_path) is None
    assert lazer_import.remove_pack(new) and not new.exists()


def fake_program(folder, lazer=True):
    folder.mkdir(parents=True)
    exe = folder / "osu!.exe"
    exe.write_bytes(b"MZ")
    if lazer:
        (folder / "osu.Game.dll").write_bytes(b"MZ")
    return exe


def test_lazer_is_told_apart_from_stable(tmp_path, monkeypatch):
    stable = fake_program(tmp_path / "osu!", lazer=False)
    lazer = fake_program(tmp_path / "osulazer" / "current")
    assert lazer_import.find_lazer([stable, lazer]) == lazer
    assert lazer_import.find_lazer([stable]) is None
    # tests (and a computer without lazer) never find the real one
    monkeypatch.setenv("OSU_COACH_NO_AUTODETECT", "1")
    assert lazer_import.find_lazer() is None


def test_long_lists_are_split_to_fit_a_command_line(tmp_path):
    files = [tmp_path / f"{i:04d} a long map set name.osz" for i in range(100)]
    groups = lazer_import.batches(files, limit=1000)
    assert [f for g in groups for f in g] == files and len(groups) > 1
    assert all(sum(len(str(f)) + 3 for f in g) <= 1000 for g in groups)


def osz_files(folder, n):
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for i in range(n):
        p = folder / f"{i + 1}.osz"
        p.write_bytes(b"PK")
        out.append(p)
    return out


def test_maps_are_handed_to_lazer_which_deletes_them(tmp_path):
    files = osz_files(tmp_path / "lazer-maps", 3)
    runs = []

    def lazer(exe, group):  # like lazer: imports each file, then deletes it
        runs.append((exe, list(group)))
        for f in group:
            f.unlink()

    seen = []
    imported, left = lazer_import.send_to_lazer(
        tmp_path / "osu!.exe", files, progress=lambda d, n, m: seen.append(m), run=lazer, sleep=lambda s: None
    )
    assert imported == files and left == [] and runs == [(tmp_path / "osu!.exe", files)]


def test_maps_lazer_doesnt_take_are_reported_after_the_wait(tmp_path):
    files = osz_files(tmp_path / "lazer-maps", 3)
    now = [0.0]

    def lazer(exe, group):
        group[0].unlink()  # takes one, not the others

    def sleep(s):
        now[0] += s

    seen = []
    imported, left = lazer_import.send_to_lazer(
        tmp_path / "osu!.exe",
        files,
        progress=lambda d, n, m: seen.append(m),
        run=lazer,
        wait_s=lambda n: 5.0,
        clock=lambda: now[0],
        sleep=sleep,
    )
    assert imported == files[:1] and left == files[1:]
    assert 4.5 <= now[0] <= 5.5 and seen[-1] == "lazer is importing the maps: 1 of 3"


def test_zip_contains_the_folder_without_maps():
    data = lazer_import.pack_zip({"osu-coach: Speed (3.1★)": MD5S}, "osu-coach: Speed (3.1★)")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        assert names == {"osu-coach Speed (3,1★)/osu!.user.cfg", "osu-coach Speed (3,1★)/collection.db"}
        assert loads(z.read("osu-coach Speed (3,1★)/collection.db"))[1] == [("osu-coach: Speed (3.1★)", MD5S)]


def test_only_sets_with_missing_difficulties_are_downloaded():
    rows = [("a" * 32, 10), ("b" * 32, 10), ("c" * 32, 11), ("d" * 32, 12)]
    assert sets_to_download(rows, {"a" * 32, "c" * 32}) == [10, 12]
    assert sets_to_download(rows, set()) == [10, 11, 12]


def test_cli_makes_the_lazer_folder(tmp_path, capsys):
    dest = tmp_path / "lazer pack"
    assert (
        main(
            [
                "playlist",
                "aim",
                "--comfort",
                "3.0",
                "--lazer",
                str(dest),
                "--no-maps",
                "--cache",
                str(tmp_path / "cache"),
                "-q",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "lazer import folder" in out and "Run setup wizard" in out
    assert (dest / "osu!.user.cfg").exists()
    name, hashes = read_collection_db(dest / "collection.db")[1][0]
    assert name.startswith("osu-coach:") and len(hashes) >= 6
