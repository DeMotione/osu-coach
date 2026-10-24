"""The one-click lazer import folder (lazer_import)."""

import io
import zipfile
from pathlib import Path

from osu_coach.cli import main
from osu_coach.exports import lazer_import
from osu_coach.exports.collection_db import loads, read_collection_db
from osu_coach.exports.domain import sets_to_download

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
