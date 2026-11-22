import shutil

from osu_coach.cli import main
from osu_coach.infra.exports.collection_db import read_collection_db
from tests.conftest import replay_and_map


def _folder(tmp_path, names):
    folder = tmp_path / "plays"
    folder.mkdir()
    for n in names:
        rp, mp, _ = replay_and_map(n)
        shutil.copy(rp, folder / n)
        shutil.copy(mp, folder / f"{n}.osu")
    return folder


def test_analyze_prints_report(tmp_path, capsys):
    folder = _folder(tmp_path, ["circlecore__legit__legit-12.osr"])
    rc = main(
        [
            "analyze",
            "--no-auto",
            "--offline",
            "--folder",
            str(folder),
            "--workers",
            "1",
            "-q",
            "--cache",
            str(tmp_path / "cache"),
            "--json",
            str(tmp_path / "r.json"),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    for section in ("osu-coach report", "Skills", "Why you miss", "Tips", "Practice plan", "Skill Development"):
        assert section in out, section
    assert (tmp_path / "r.json").stat().st_size > 1000


def test_playlist_from_comfort_level_writes_collection(tmp_path, capsys):
    db = tmp_path / "collection.db"
    rc = main(
        [
            "playlist",
            "aim",
            "--comfort",
            "3",
            "--maps",
            "6",
            "--collection",
            str(db),
            "--cache",
            str(tmp_path / "cache"),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0 and "Warm-up" in out and "https://osu.ppy.sh/beatmapsets/" in out
    _, cols = read_collection_db(db)
    assert len(cols) == 1 and cols[0][0].startswith("osu-coach: Jumps") and len(cols[0][1]) == 6


def test_locate_runs(capsys):
    assert main(["locate"]) == 0
    assert capsys.readouterr().out.strip()


def test_analyze_only_these_files_best_and_level(tmp_path, capsys):
    from osu_coach.infra.settings import load_settings

    folder = _folder(tmp_path, ["circlecore__legit__legit-12.osr", "osrparse__resources__replay.osr"])
    cache = tmp_path / "cache"
    one = folder / "circlecore__legit__legit-12.osr"
    rc = main(
        [
            "analyze",
            "--only",
            str(one),
            "--folder",
            str(folder),
            "--offline",
            "--workers",
            "1",
            "-q",
            "--cache",
            str(cache),
            "--best",
            "--level",
            "5",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "1 best replays" in out and "Best replays = only passed plays" in out
    assert "Level 5.00★ (set with --level)" in out
    assert load_settings(cache)["replay_set"] == "best"  # remembered, like the app's switch
    rc = main(["analyze", "--only", str(one), "--offline", "--workers", "1", "-q", "--cache", str(cache)])
    assert rc == 0 and "1 best replays" in capsys.readouterr().out
    rc = main(
        [
            "analyze",
            "--only",
            str(one),
            "--offline",
            "--workers",
            "1",
            "-q",
            "--cache",
            str(cache),
            "--all-replays",
            "--since",
            "2000-01-01",
            "--until",
            "2100-01-01",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0 and "1 replays" in out and load_settings(cache)["replay_set"] == "all"


def test_analyze_reads_the_installs_the_app_reads(tmp_path, capsys):
    """The installs entered in the app are read, and one switched off in its Settings isn't (the same plays, #133)."""
    import hashlib

    import pytest

    from osu_coach.infra.settings import save_settings
    from tests.conftest import MOT1ONE, sample_paths

    root = tmp_path / "lazer"  # a lazer data folder: its replays and maps in the file store
    (root / "files").mkdir(parents=True)
    (root / "client.realm").write_bytes(b"")
    for name in MOT1ONE:
        for p in sample_paths(name):
            data = p.read_bytes()
            h = hashlib.sha256(data).hexdigest()
            (root / "files" / h[0] / h[:2]).mkdir(parents=True, exist_ok=True)
            (root / "files" / h[0] / h[:2] / h).write_bytes(data)
    cache = tmp_path / "cache"
    save_settings({"install_paths": [str(root)], "skipped_installs": [str(root)]}, cache)
    with pytest.raises(SystemExit, match="No osu!standard replays found"):
        main(["analyze", "--offline", "--workers", "1", "--cache", str(cache)])
    assert "skipping osu!lazer" in capsys.readouterr().err  # switched off in the app
    save_settings({"install_paths": [str(root)], "skipped_installs": []}, cache)
    assert main(["analyze", "--offline", "--workers", "1", "-q", "--cache", str(cache)]) == 0
    assert "Mot1one" in capsys.readouterr().out
