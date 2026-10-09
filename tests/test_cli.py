import shutil

from osu_coach.cli import main
from osu_coach.collection_db import read_collection_db
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
    rc = main(["analyze", "--no-auto", "--offline", "--folder", str(folder), "--workers", "1", "-q",
               "--cache", str(tmp_path / "cache"), "--json", str(tmp_path / "r.json")])
    out = capsys.readouterr().out
    assert rc == 0
    for section in ("osu-coach report", "Skills", "Why you miss", "Tips", "Practice plan", "Suggested maps"):
        assert section in out, section
    assert (tmp_path / "r.json").stat().st_size > 1000


def test_playlist_from_comfort_level_writes_collection(tmp_path, capsys):
    db = tmp_path / "collection.db"
    rc = main(["playlist", "aim", "--comfort", "3", "--maps", "6", "--collection", str(db),
               "--cache", str(tmp_path / "cache")])
    out = capsys.readouterr().out
    assert rc == 0 and "Warm-up" in out and "https://osu.ppy.sh/beatmapsets/" in out
    _, cols = read_collection_db(db)
    assert len(cols) == 1 and cols[0][0].startswith("osu-coach: Jump aim") and len(cols[0][1]) == 6


def test_locate_runs(capsys):
    assert main(["locate"]) == 0
    assert capsys.readouterr().out.strip()
