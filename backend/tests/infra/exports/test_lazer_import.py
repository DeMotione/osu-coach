"""Getting maps into osu!lazer and opening them there (lazer_import)."""

import os
import zipfile
from pathlib import Path

import pytest

from osu_coach.cli import main
from osu_coach.domain.exports.downloads import sets_to_download
from osu_coach.infra.beatmaps import sources
from osu_coach.infra.exports import lazer_import


def test_folder_names_have_no_dots_or_forbidden_characters():
    name = lazer_import.safe_name('osu-coach: Aim (2.5★) <a/b\\c|d?e*"f>')
    assert "." not in name and not set(name) & set('\\/:*?"<>|')
    assert name.startswith("osu-coach Aim (2,5★)")
    assert lazer_import.safe_name(":::") == "osu-coach playlist"


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


def fake_download(set_id, dest, progress=None, stop=None):
    """An .osz for every set but 3, which can't be downloaded."""
    if set_id == 3:
        return None
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    osz = dest / f"{set_id} Artist - Title.osz"
    with zipfile.ZipFile(osz, "w") as z:
        z.writestr("Artist - Title (mapper) [Easy].osu", "osu file format v14\n")
    return osz


@pytest.fixture
def lazer(monkeypatch, tmp_path):
    """A lazer that imports each .osz it is handed and deletes it, as the real one does."""
    handed = []

    def run(exe, args):
        handed.append((exe, list(args)))
        for a in args:
            if str(a).endswith(".osz"):
                Path(a).unlink()

    monkeypatch.setattr(lazer_import, "launch", run)
    monkeypatch.setattr(sources, "download_osz", fake_download)
    return handed


def test_downloads_go_to_lazer_and_nothing_stays_behind(tmp_path, lazer):
    folder = tmp_path / "lazer-maps"
    folder.mkdir()
    stale, busy = folder / "old.osz", folder / "busy.osz"
    for f in (stale, busy):
        f.write_bytes(b"PK")
    os.utime(stale, (0, 0))  # left from long ago; ``busy`` lazer may still be taking
    res = lazer_import.download_and_send(tmp_path / "osu!.exe", [1, 3, 2, 2], folder)
    assert res == {"maps": [1, 2], "failed": [3], "imported": [1, 2], "not_imported": []}
    assert [Path(f).name for f in lazer[0][1]] == ["1 Artist - Title.osz", "2 Artist - Title.osz"]
    assert sorted(p.name for p in folder.iterdir()) == ["busy.osz"]


def test_a_map_is_opened_with_its_link(tmp_path, lazer):
    assert lazer_import.open_map(tmp_path / "osu!.exe", 2768184) == "osu://b/2768184"
    assert lazer == [(tmp_path / "osu!.exe", ["osu://b/2768184"])]


def test_the_link_reaches_lazer_as_it_is(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(lazer_import.subprocess, "Popen", lambda args, **kw: calls.append(args))
    lazer_import.open_map(tmp_path / "osu!.exe", 5)
    assert calls == [[str(tmp_path / "osu!.exe"), "osu://b/5"]]  # not turned into a path (osu:\\b\\5)


def test_only_sets_with_missing_difficulties_are_downloaded():
    rows = [("a" * 32, 10), ("b" * 32, 10), ("c" * 32, 11), ("d" * 32, 12)]
    assert sets_to_download(rows, {"a" * 32, "c" * 32}) == [10, 12]
    assert sets_to_download(rows, set()) == [10, 11, 12]


def test_cli_sends_the_playlist_maps_to_lazer(tmp_path, capsys, monkeypatch, lazer):
    exe = tmp_path / "osu!.exe"
    monkeypatch.setattr(lazer_import, "find_lazer", lambda candidates=None: exe)
    cache = tmp_path / "cache"
    assert main(["playlist", "aim", "--comfort", "3.0", "--lazer", "--cache", str(cache), "-q"]) == 0
    assert "lazer imported" in capsys.readouterr().out
    sent = [Path(f) for _, files in lazer for f in files]
    assert sent and all(f.parent == cache / "lazer-maps" for f in sent)
    assert not list((cache / "lazer-maps").glob("*.osz"))

    monkeypatch.setattr(lazer_import, "find_lazer", lambda candidates=None: None)
    with pytest.raises(SystemExit, match="osu!lazer wasn't found"):
        main(["playlist", "aim", "--comfort", "3.0", "--lazer", "--cache", str(cache), "-q"])
