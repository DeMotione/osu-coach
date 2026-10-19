import os
import subprocess
import sys
from pathlib import Path

import pytest

from osu_coach.replays import detect
from osu_coach.replays.detect import (
    Install,
    find_installs,
    install_at,
    is_osu_running,
    lazer_candidates,
    lazer_install,
    stable_candidates,
    stable_install,
)

posix_only = pytest.mark.skipif(os.name == "nt", reason="the Linux/macOS candidate lists")
linux_only = pytest.mark.skipif(sys.platform != "linux", reason="XDG data folders")


@pytest.fixture
def home(monkeypatch, tmp_path):
    """A home folder of its own, so candidate lists never touch the real one."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("USERPROFILE", str(h))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return h


def touch(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_stable(root: Path) -> Path:
    """The smallest folder that counts as a stable install."""
    (root / "Songs").mkdir(parents=True)
    return root


def make_lazer(root: Path) -> Path:
    (root / "files").mkdir(parents=True)
    touch(root / "client.realm")
    return root


# ------------------------------------------------------------------ Install
def test_install_label_names_kind_and_folder(tmp_path):
    assert Install("stable", tmp_path).label == f"osu!stable – {tmp_path}"
    assert Install("lazer", tmp_path).label.startswith("osu!lazer – ")


def test_install_defaults_do_not_share_replay_lists(tmp_path):
    a, b = Install("stable", tmp_path), Install("stable", tmp_path)
    a.replay_dirs.append(tmp_path)
    assert b.replay_dirs == []


# ------------------------------------------------------------------ stable_install
def test_stable_install_missing_folder_or_file(tmp_path):
    assert stable_install(tmp_path / "nope") is None
    assert stable_install(touch(tmp_path / "file.txt")) is None


def test_stable_install_empty_folder_is_not_an_install(tmp_path):
    assert stable_install(tmp_path) is None


def test_stable_install_ignores_unrelated_files(tmp_path):
    touch(tmp_path / "osu!.cfg")  # the generic config is not a marker on its own
    touch(tmp_path / "readme.txt")
    (tmp_path / "Replays").mkdir()  # exported replays alone do not make an install either
    assert stable_install(tmp_path) is None


@pytest.mark.parametrize(
    "marker",
    ["osu!.db", "Songs/", "osu!.alice.cfg", "Data/r/"],
)
def test_stable_install_recognised_by_each_marker(tmp_path, marker):
    if marker.endswith("/"):
        (tmp_path / marker).mkdir(parents=True)
    else:
        touch(tmp_path / marker)
    inst = stable_install(tmp_path)
    assert inst is not None and inst.kind == "stable" and inst.root == tmp_path
    assert inst.files_dir is None


def test_stable_install_accepts_a_string_path(tmp_path):
    assert stable_install(str(make_stable(tmp_path / "osu!"))).root == tmp_path / "osu!"


def test_stable_install_full_layout(tmp_path):
    root = make_stable(tmp_path)
    (root / "Data" / "r").mkdir(parents=True)
    (root / "Replays").mkdir()
    touch(root / "collection.db")
    inst = stable_install(root)
    assert inst.songs == root / "Songs"
    assert inst.replay_dirs == [root / "Data" / "r", root / "Replays"]  # automatic saves first, then F2 exports
    assert inst.collection_db == root / "collection.db"


def test_stable_install_lists_only_existing_replay_folders(tmp_path):
    root = make_stable(tmp_path)
    assert stable_install(root).replay_dirs == []
    (root / "Replays").mkdir()
    assert stable_install(root).replay_dirs == [root / "Replays"]


def test_stable_install_without_songs_folder(tmp_path):
    touch(tmp_path / "osu!.db")
    assert stable_install(tmp_path).songs is None


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ([], None),
        (["collection.db"], "collection.db"),
        (["osu!.db"], "collection.db"),  # osu!.db present: the game writes collection.db there on exit
        (["osu!.db", "collection.db"], "collection.db"),
    ],
)
def test_stable_install_collection_db(tmp_path, files, expected):
    make_stable(tmp_path)
    for f in files:
        touch(tmp_path / f)
    inst = stable_install(tmp_path)
    assert inst.collection_db == (tmp_path / expected if expected else None)


def test_stable_install_reads_relative_beatmap_directory(tmp_path):
    (tmp_path / "Maps" / "x").mkdir(parents=True)
    touch(tmp_path / "osu!.alice.cfg", "Username = alice\nBeatmapDirectory = Maps\n")
    assert stable_install(tmp_path).songs == tmp_path / "Maps"


def test_stable_install_reads_absolute_beatmap_directory(tmp_path):
    elsewhere = tmp_path / "elsewhere" / "Songs"
    elsewhere.mkdir(parents=True)
    root = tmp_path / "osu!"
    (root / "Songs").mkdir(parents=True)
    touch(root / "osu!.alice.cfg", f"BeatmapDirectory = {elsewhere}\n")
    assert stable_install(root).songs == elsewhere


def test_stable_install_beatmap_directory_survives_bom_and_spacing(tmp_path):
    (tmp_path / "Maps").mkdir()
    (tmp_path / "osu!.alice.cfg").write_bytes(b"\xef\xbb\xbf  BeatmapDirectory   =   Maps  \r\nOther = 1\r\n")
    assert stable_install(tmp_path).songs == tmp_path / "Maps"


def test_stable_install_ignores_beatmap_directory_that_does_not_exist(tmp_path):
    (tmp_path / "Songs").mkdir()
    touch(tmp_path / "osu!.alice.cfg", "BeatmapDirectory = Gone\n")
    assert stable_install(tmp_path).songs == tmp_path / "Songs"


def test_stable_install_songs_is_none_when_neither_default_nor_configured_exists(tmp_path):
    touch(tmp_path / "osu!.alice.cfg", "BeatmapDirectory = Gone\n")
    inst = stable_install(tmp_path)
    assert inst is not None and inst.songs is None


@pytest.mark.parametrize("text", ["BeatmapDirectory =\n", "beatmapdirectory = Maps\n", "no equals sign here\n", "\n"])
def test_stable_install_ignores_empty_wrongly_cased_or_malformed_config_lines(tmp_path, text):
    (tmp_path / "Maps").mkdir()
    touch(tmp_path / "osu!.alice.cfg", text)
    assert stable_install(tmp_path).songs is None  # no Songs folder and no valid setting


def test_stable_install_tolerates_undecodable_config(tmp_path):
    (tmp_path / "Maps").mkdir()
    (tmp_path / "osu!.alice.cfg").write_bytes(b"\xff\xfe\x00junk\nBeatmapDirectory = Maps\n")
    assert stable_install(tmp_path).songs == tmp_path / "Maps"


def test_stable_install_config_that_is_a_folder_is_skipped(tmp_path):
    (tmp_path / "Songs").mkdir()
    (tmp_path / "osu!.broken.cfg").mkdir()  # reading it raises OSError
    assert stable_install(tmp_path).songs == tmp_path / "Songs"


def test_stable_install_generic_osu_cfg_is_not_a_user_config(tmp_path):
    (tmp_path / "Maps").mkdir()
    (tmp_path / "Songs").mkdir()
    touch(tmp_path / "osu!.cfg", "BeatmapDirectory = Maps\n")
    assert stable_install(tmp_path).songs == tmp_path / "Songs"


# ------------------------------------------------------------------ lazer_install
def test_lazer_install_missing_folder(tmp_path):
    assert lazer_install(tmp_path / "nope") is None
    assert lazer_install(tmp_path) is None


@pytest.mark.parametrize("marker", ["client.realm", "framework.ini"])
def test_lazer_install_needs_files_folder_and_a_marker(tmp_path, marker):
    (tmp_path / "files").mkdir()
    assert lazer_install(tmp_path) is None  # files/ alone
    touch(tmp_path / marker)
    inst = lazer_install(tmp_path)
    assert inst.kind == "lazer" and inst.root == tmp_path
    assert inst.files_dir == tmp_path / "files"
    assert inst.songs is None and inst.collection_db is None


def test_lazer_install_marker_without_files_folder(tmp_path):
    touch(tmp_path / "client.realm")
    assert lazer_install(tmp_path) is None


def test_lazer_install_files_must_be_a_folder(tmp_path):
    touch(tmp_path / "files")
    touch(tmp_path / "client.realm")
    assert lazer_install(tmp_path) is None


def test_lazer_install_replay_dirs_only_when_exports_exist(tmp_path):
    make_lazer(tmp_path)
    assert lazer_install(tmp_path).replay_dirs == []
    (tmp_path / "exports").mkdir()
    assert lazer_install(tmp_path).replay_dirs == [tmp_path / "exports"]


def test_lazer_and_stable_do_not_recognise_each_others_folders(tmp_path):
    assert stable_install(make_lazer(tmp_path / "lazer")) is None
    assert lazer_install(make_stable(tmp_path / "stable")) is None


# ------------------------------------------------------------------ find_installs
def test_find_installs_checks_explicit_roots(tmp_path):
    stable = make_stable(tmp_path / "stable")
    lazer = make_lazer(tmp_path / "lazer")
    found = find_installs([stable, tmp_path / "empty"], [lazer, tmp_path / "empty"])
    assert [(i.kind, i.root) for i in found] == [("stable", stable), ("lazer", lazer)]


def test_find_installs_accepts_strings(tmp_path):
    stable = make_stable(tmp_path / "stable")
    assert [i.root for i in find_installs([str(stable)], [])] == [stable]


def test_find_installs_skips_missing_roots_and_returns_nothing_for_no_roots(tmp_path):
    assert find_installs([], []) == []
    assert find_installs([tmp_path / "a", tmp_path / "b"], [tmp_path / "c"]) == []


def test_find_installs_lists_a_root_once(tmp_path):
    stable = make_stable(tmp_path / "stable")
    found = find_installs([stable, stable, stable / ".." / "stable"], [])
    assert len(found) == 1


def test_find_installs_lists_a_symlinked_root_once(tmp_path):
    stable = make_stable(tmp_path / "stable")
    link = tmp_path / "link"
    try:
        link.symlink_to(stable, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not available")
    assert len(find_installs([stable, link], [])) == 1


def test_install_at_recognises_either_kind_and_the_exe_itself(tmp_path):
    stable = make_stable(tmp_path / "stable")
    lazer = make_lazer(tmp_path / "lazer")
    assert install_at(stable).kind == "stable" and install_at(lazer).kind == "lazer"
    assert install_at(touch(stable / "osu!.exe")).root == stable
    assert install_at(tmp_path / "missing") is None and install_at(tmp_path) is None


def test_find_installs_adds_the_extra_folders_once(tmp_path):
    stable = make_stable(tmp_path / "stable")
    lazer = make_lazer(tmp_path / "lazer")
    found = find_installs([stable], [], extra=[stable, lazer, tmp_path / "missing"])
    assert [(i.kind, i.root) for i in found] == [("stable", stable), ("lazer", lazer)]


def test_find_installs_keeps_stable_order(tmp_path):
    a = make_stable(tmp_path / "b")
    b = make_stable(tmp_path / "a")
    assert [i.root for i in find_installs([a, b], [])] == [a, b]  # given order, not sorted


def test_find_installs_without_autodetect_ignores_the_candidates(monkeypatch, tmp_path):
    def boom():
        raise AssertionError("the computer must not be searched")

    monkeypatch.setattr(detect, "stable_candidates", boom)
    monkeypatch.setattr(detect, "lazer_candidates", boom)
    monkeypatch.setenv("OSU_COACH_NO_AUTODETECT", "1")
    assert find_installs() == []
    lazer = make_lazer(tmp_path / "lazer")
    assert [i.root for i in find_installs(lazer_roots=[lazer])] == [lazer]  # explicit roots are still checked


@pytest.mark.parametrize("value", ["", "0", " 0 ", "  "])
def test_find_installs_searches_candidates_unless_autodetect_is_off(monkeypatch, tmp_path, value):
    stable = make_stable(tmp_path / "stable")
    lazer = make_lazer(tmp_path / "lazer")
    monkeypatch.setattr(detect, "stable_candidates", lambda: [stable])
    monkeypatch.setattr(detect, "lazer_candidates", lambda: [lazer])
    monkeypatch.setenv("OSU_COACH_NO_AUTODETECT", value)
    assert [i.kind for i in find_installs()] == ["stable", "lazer"]


def test_find_installs_unset_variable_searches_candidates(monkeypatch, tmp_path):
    stable = make_stable(tmp_path / "stable")
    monkeypatch.setattr(detect, "stable_candidates", lambda: [stable])
    monkeypatch.setattr(detect, "lazer_candidates", lambda: [])
    monkeypatch.delenv("OSU_COACH_NO_AUTODETECT")
    assert [i.root for i in find_installs()] == [stable]


def test_find_installs_explicit_roots_replace_the_candidates_of_that_kind(monkeypatch, tmp_path):
    cand = make_stable(tmp_path / "candidate")
    given = make_stable(tmp_path / "given")
    monkeypatch.setattr(detect, "stable_candidates", lambda: [cand])
    monkeypatch.setattr(detect, "lazer_candidates", lambda: [])
    monkeypatch.setenv("OSU_COACH_NO_AUTODETECT", "0")
    assert [i.root for i in find_installs(stable_roots=[given])] == [given]


# ------------------------------------------------------------------ stable_candidates
@posix_only
def test_stable_candidates_start_with_the_saved_osu_path(home):
    osupath = home / ".local/share/osuconfig/osupath"
    touch(osupath, "/games/osu\n")
    assert stable_candidates()[0] == Path("/games/osu")


@posix_only
def test_stable_candidates_without_a_saved_osu_path(home):
    c = stable_candidates()
    assert home / ".local/share/osu-wine/OSU" in c
    assert c[0] == home / ".local/share/osu-wine/OSU"


@posix_only
def test_stable_candidates_cover_wine_prefixes_for_the_current_user(home, monkeypatch):
    monkeypatch.setattr(detect.getpass, "getuser", lambda: "alice")
    c = stable_candidates()
    assert home / ".wine/drive_c/osu!" in c
    assert home / ".wine/drive_c/users/alice/AppData/Local/osu!" in c
    assert home / ".wine_osu/drive_c/users/alice/Local Settings/Application Data/osu!" in c
    assert len(c) == len(set(c))


@posix_only
def test_stable_candidates_fall_back_to_the_user_variable(home, monkeypatch):
    def fail():
        raise OSError("no user")

    monkeypatch.setattr(detect.getpass, "getuser", fail)
    monkeypatch.setenv("USER", "bob")
    assert home / ".wine/drive_c/users/bob/AppData/Local/osu!" in stable_candidates()


@linux_only
def test_stable_candidates_macos_app_bundle_only_on_darwin(home, monkeypatch):
    bundle = home / "Applications/osu!.app/Contents/Resources/drive_c/osu!"
    assert bundle not in stable_candidates()
    monkeypatch.setattr(detect.sys, "platform", "darwin")
    assert bundle in stable_candidates()


@posix_only
def test_stable_candidates_find_a_wine_install(home):
    root = make_stable(home / ".wine/drive_c/osu!")
    assert root in stable_candidates()
    assert [i.root for i in find_installs(stable_candidates(), [])] == [root]


# ------------------------------------------------------------------ lazer_candidates
@linux_only
def test_lazer_candidates_default_to_xdg_data_home_under_home(home):
    assert lazer_candidates() == [home / ".local/share/osu", home / ".local/share/osu-lazer"]


@linux_only
def test_lazer_candidates_follow_xdg_data_home(home, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert lazer_candidates() == [tmp_path / "xdg/osu", tmp_path / "xdg/osu-lazer"]
    monkeypatch.setenv("XDG_DATA_HOME", "")  # an empty value counts as unset
    assert lazer_candidates()[0] == home / ".local/share/osu"


@linux_only
def test_lazer_candidates_put_a_moved_data_folder_first(home):
    touch(home / ".local/share/osu/storage.ini", "FullPath = /data/osu-moved\n")
    c = lazer_candidates()
    assert c[0] == Path("/data/osu-moved")
    assert c[1:] == [home / ".local/share/osu", home / ".local/share/osu-lazer"]


@linux_only
def test_lazer_candidates_storage_ini_is_case_insensitive_and_bom_tolerant(home):
    (home / ".local/share/osu").mkdir(parents=True)
    (home / ".local/share/osu/storage.ini").write_bytes(b"\xef\xbb\xbf  fullpath=/data/moved \r\n")
    assert lazer_candidates()[0] == Path("/data/moved")


@linux_only
@pytest.mark.parametrize("text", ["FullPath =\n", "Other = /x\n", "just text\n", ""])
def test_lazer_candidates_ignore_empty_or_unrelated_storage_ini(home, text):
    touch(home / ".local/share/osu/storage.ini", text)
    assert lazer_candidates() == [home / ".local/share/osu", home / ".local/share/osu-lazer"]


@linux_only
def test_lazer_candidates_read_the_storage_ini_of_both_folders(home):
    touch(home / ".local/share/osu/storage.ini", "FullPath = /one\n")
    touch(home / ".local/share/osu-lazer/storage.ini", "FullPath = /two\n")
    assert lazer_candidates()[:2] == [Path("/two"), Path("/one")]  # each is inserted at the front in turn


@linux_only
def test_lazer_candidates_unreadable_storage_ini_is_skipped(home):
    (home / ".local/share/osu/storage.ini").mkdir(parents=True)  # a folder: read_text raises OSError
    assert lazer_candidates() == [home / ".local/share/osu", home / ".local/share/osu-lazer"]


@linux_only
def test_lazer_candidates_find_a_moved_install(home, tmp_path):
    moved = make_lazer(tmp_path / "moved")
    touch(home / ".local/share/osu/storage.ini", f"FullPath = {moved}\n")
    assert [i.root for i in find_installs([], lazer_candidates())] == [moved]


# ------------------------------------------------------------------ is_osu_running
def as_windows(monkeypatch, stdout=None, error=None):
    """Make is_osu_running take its Windows branch, with ``tasklist`` replaced."""
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        if error:
            raise error
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(detect.subprocess, "run", run)
    return calls


def call_as_windows(monkeypatch) -> bool:
    with monkeypatch.context() as m:
        m.setattr(detect.os, "name", "nt")  # only for the call: pathlib must not see it
        return is_osu_running()


def test_is_osu_running_windows_finds_the_process_in_the_task_list(monkeypatch):
    calls = as_windows(monkeypatch, stdout="Image Name  PID\nosu!.exe  1234\n")
    assert call_as_windows(monkeypatch) is True
    assert calls and calls[0][0] == "tasklist"


def test_is_osu_running_windows_without_the_process(monkeypatch):
    as_windows(monkeypatch, stdout="INFO: No tasks are running which match the specified criteria.\n")
    assert call_as_windows(monkeypatch) is False


@pytest.mark.parametrize(
    "error", [FileNotFoundError("tasklist"), subprocess.TimeoutExpired("tasklist", 10), OSError("x")]
)
def test_is_osu_running_windows_errors_mean_not_running(monkeypatch, error):
    as_windows(monkeypatch, error=error)
    assert call_as_windows(monkeypatch) is False


@posix_only
def test_is_osu_running_linux_scans_process_command_lines(monkeypatch):
    cmdlines = {
        "1": b"/sbin/init\x00",
        "42": b"Z:\\home\\me\\osu\\osu!.exe\x00-devserver\x00",
    }
    monkeypatch.setattr(detect.os, "listdir", lambda p: ["self", "1", "42", "net"])
    monkeypatch.setattr(Path, "read_bytes", lambda self: cmdlines[self.parent.name])
    assert is_osu_running() is True


@posix_only
def test_is_osu_running_linux_without_the_process(monkeypatch):
    monkeypatch.setattr(detect.os, "listdir", lambda p: ["1", "2"])
    monkeypatch.setattr(Path, "read_bytes", lambda self: b"/usr/bin/python3\x00-m\x00osu_coach\x00")
    assert is_osu_running() is False  # "osu_coach" is not "osu!.exe"


@posix_only
def test_is_osu_running_linux_skips_processes_that_vanish(monkeypatch):
    def read_bytes(self):
        if self.parent.name == "10":
            raise FileNotFoundError(self)  # exited while we were looking
        if self.parent.name == "11":
            raise PermissionError(self)
        return b"osu!.exe\x00"

    monkeypatch.setattr(detect.os, "listdir", lambda p: ["10", "11", "12"])
    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    assert is_osu_running() is True


@posix_only
def test_is_osu_running_linux_ignores_non_numeric_entries(monkeypatch):
    seen = []

    def read_bytes(self):
        seen.append(self.parent.name)
        return b"osu!.exe\x00"

    monkeypatch.setattr(detect.os, "listdir", lambda p: ["sys", "cpuinfo", "7x"])
    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    assert is_osu_running() is False
    assert seen == []


@posix_only
def test_is_osu_running_linux_unreadable_proc_means_not_running(monkeypatch):
    def listdir(p):
        raise FileNotFoundError(p)

    monkeypatch.setattr(detect.os, "listdir", listdir)
    assert is_osu_running() is False


def test_is_osu_running_never_raises(monkeypatch):
    def listdir(p):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(detect.os, "listdir", listdir)
    monkeypatch.setattr(detect.subprocess, "run", lambda *a, **k: listdir(a))
    assert is_osu_running() is False
