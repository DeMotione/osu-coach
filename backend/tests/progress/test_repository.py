"""Progress by month, stored in SQLite: plays, maps, star rating and skills per month."""

import datetime as dt
import shutil

import numpy as np
import pandas as pd
import pytest

from osu_coach.analysis.domain import ReplayAnalysis
from osu_coach.cli import main
from osu_coach.library.repository import Library, analyze_files
from osu_coach.profile.domain import build_profile
from osu_coach.progress import domain as domain_progress
from osu_coach.progress import repository as progress
from tests.conftest import replay_and_map

UTC = dt.UTC
EEST = dt.timezone(dt.timedelta(hours=3))  # Tallinn in summer
MINE = ["mot1one__lazer_nm.osr", "mot1one__lazer_dthd_spinner.osr", "mot1one__lazer_failed.osr"]


def _fake(key, date, md5="a" * 32, stars=5.0, misses=0, n=500, completed=True, combo=700, player="P", length=120.0):
    meta = {
        "key": key,
        "player": player,
        "date": date,
        "beatmap_md5": md5,
        "beatmap_id": 1,
        "beatmapset_id": 1,
        "artist": "Artist",
        "title": f"Map {md5[:4]}",
        "version": "Insane",
        "creator": "C",
        "mods": 0,
        "mod_string": "",
        "rate": 1.0,
        "client": "lazer",
        "stars": stars,
        "aim": stars / 2,
        "speed": stars / 2,
        "bpm": 180.0,
        "length_s": length,
        "ar": 9.0,
        "od": 8.0,
        "cs": 4.0,
        "accuracy": 0.95,
        "n300": n - misses,
        "n100": 0,
        "n50": 0,
        "nmiss": misses,
        "head_misses": misses,
        "n_objects": n,
        "n_played": n if completed else n // 2,
        "completed": completed,
        "max_combo": combo if not misses else 100,
        "map_max_combo": 700,
        "ur": 150.0,
        "score": 1,
    }
    return ReplayAnalysis(key, meta, pd.DataFrame(), pd.DataFrame())


def test_plays_are_stored_once_and_kept(tmp_path):
    conn = progress.connect(tmp_path)
    plays = [_fake("k1", dt.datetime(2026, 9, 1, 12)), _fake("k2", dt.datetime(2026, 9, 2, 12))]
    assert progress.record(conn, plays, UTC) == 2
    assert progress.record(conn, plays, UTC) == 0  # the same replays again
    conn.close()
    assert progress.players(progress.connect(tmp_path)) == [("P", 2)]
    assert (tmp_path / "progress.sqlite").is_file()


def _two_months(tmp_path):
    conn = progress.connect(tmp_path)
    progress.record(
        conn,
        [
            _fake("a1", dt.datetime(2026, 8, 5), md5="a" * 32, stars=5.0),
            _fake("a2", dt.datetime(2026, 8, 6), md5="b" * 32, stars=5.6, misses=20),  # passed, with misses
            _fake("s1", dt.datetime(2026, 9, 5), md5="a" * 32, stars=5.0),  # the same map again
            _fake("s2", dt.datetime(2026, 9, 6), md5="c" * 32, stars=6.2),  # FC of a harder map
            _fake("s3", dt.datetime(2026, 9, 7), md5="d" * 32, stars=7.0, completed=False, misses=40),  # failed
        ],
        UTC,
    )
    return conn


def test_monthly_plays_maps_and_star_rating(tmp_path):
    m = progress.monthly(_two_months(tmp_path), "P").set_index("month")
    assert list(m.index) == ["2026-08", "2026-09"]
    sep, aug = m.loc["2026-09"], m.loc["2026-08"]
    assert (sep["plays"], sep["maps"], sep["new_maps"]) == (3, 3, 2)
    assert (aug["max_stars_passed"], aug["max_stars_fc"]) == (5.6, 5.0)
    assert (sep["max_stars_passed"], sep["max_stars_fc"]) == (6.2, 6.2)
    assert sep["comfort_stars"] > aug["comfort_stars"]
    assert sep["minutes"] == pytest.approx(6.0)


def test_hardest_pass_ignores_plays_finished_with_many_misses(tmp_path):
    conn = _two_months(tmp_path)
    progress.record(conn, [_fake("s4", dt.datetime(2026, 9, 8), md5="e" * 32, stars=9.0, misses=60, n=500)], UTC)
    m = progress.monthly(conn, "P").set_index("month")
    assert m.loc["2026-09", "max_stars_passed"] == 6.2  # 12 misses per 100 notes is no real pass


def test_month_plays_lists_the_maps_of_a_month(tmp_path):
    plays = progress.month_plays(_two_months(tmp_path), "P", "2026-09")
    assert len(plays) == 3 and set(plays["title"]) == {"Map aaaa", "Map cccc", "Map dddd"}
    assert list(plays["played_at"]) == sorted(plays["played_at"], reverse=True)


def test_progress_by_day_and_week_in_a_date_range(tmp_path):
    conn = _two_months(tmp_path)
    days = progress.by_period(conn, "P", "day", tz=UTC)
    assert len(days) >= 4 and all(len(k) == 10 for k in days["month"])  # YYYY-MM-DD
    assert days["plays"].sum() == progress.monthly(conn, "P")["plays"].sum()
    weeks = progress.by_period(conn, "P", "week", tz=UTC)
    assert all("-W" in k for k in weeks["month"])
    sep = progress.by_period(conn, "P", "day", since=dt.date(2026, 9, 1), until=dt.date(2026, 9, 30), tz=UTC)
    assert sep["plays"].sum() == 3 and all(k.startswith("2026-09") for k in sep["month"])
    first = sep["month"].iloc[0]
    assert len(progress.month_plays(conn, "P", first, "day", tz=UTC)) == sep["plays"].iloc[0]


# ------------------------------------------------------------------ skills by month (needs real analyses)
@pytest.fixture(scope="module")
def nm():
    return analyze_files(*replay_and_map("mot1one__lazer_nm.osr")[:2])


def _copy(a, key, date, miss_share=0.0, seed=0):
    o = a.objects.copy()
    if miss_share:
        jumps = o.index[o["pattern"].isin(["jump", "spaced"]) & o["head_hit"]]
        flip = np.random.default_rng(seed).choice(jumps, int(len(jumps) * miss_share), replace=False)
        o.loc[flip, "head_hit"] = False
        o.loc[flip, "miss_reason"] = "aim"
    meta = dict(a.meta, key=key, date=date, beatmap_md5=f"{a.meta.get('beatmap_md5')}-{key}")  # one map each
    if miss_share:  # misses break the combo: jump aim counts distance x speed x combo
        meta["max_combo"] = int((meta.get("map_max_combo") or 0) * max(0.05, 1 - 4 * miss_share))
    return ReplayAnalysis(key, meta, o, a.presses.copy())


def _months(nm):
    """August: the sample play five times with 15% of its jumps missed; September: five times clean."""
    early = [_copy(nm, f"e{i}", dt.datetime(2026, 8, 10 + i), miss_share=0.15, seed=i) for i in range(5)]
    late = [_copy(nm, f"l{i}", dt.datetime(2026, 9, 10 + i)) for i in range(5)]
    return early, late


def test_skills_by_month_show_improvement(tmp_path, nm):
    # same maps, more aim misses in August: rated at one comfort level, September's aim is better.
    # (Rating each month at its own comfort level would put both months near 50.)
    early, late = _months(nm)
    conn = progress.connect(tmp_path)
    progress.record(conn, early + late, UTC)
    progress.rebuild_months(conn, "Mot1one", early + late, UTC)
    m = progress.monthly(conn, "Mot1one").set_index("month")
    assert m.loc["2026-09", "skill_aim"] > m.loc["2026-08", "skill_aim"] + 3
    assert m.loc["2026-09", "skill_speed"] == m.loc["2026-08", "skill_speed"]  # the misses were jumps only
    assert m.loc["2026-09", "stream_bpm"] == m.loc["2026-08", "stream_bpm"] or m["stream_bpm"].isna().all()


def test_skills_by_month_are_the_overviews_ratings(tmp_path, nm):
    """A month's skills are the ratings the Overview shows for its plays, at the comfort level of all plays (#34)."""
    early, late = _months(nm)
    conn = progress.connect(tmp_path)
    progress.record(conn, early + late, UTC)
    progress.rebuild_months(conn, "Mot1one", early + late, UTC)
    m = progress.monthly(conn, "Mot1one").set_index("month")
    overview = build_profile(early + late)  # the Overview of every play
    reference = overview.levels["comfort_stars"]
    assert m["skill_reference_stars"].tolist() == [reference, reference]
    september = build_profile(late, level=reference).skill_ratings
    for skill, rating in september.items():
        saved = m.loc["2026-09", f"skill_{skill}"]
        assert (saved != saved and rating["score"] is None) or saved == rating["score"], skill


def test_skills_saved_by_older_versions_are_not_shown(tmp_path):
    """Scores of the earlier rating scale (no reference saved with them) would mix two scales in one chart."""
    conn = _two_months(tmp_path)
    with conn:
        conn.executemany(
            "INSERT INTO month_metrics VALUES ('P', ?, ?, ?, 0, '')",
            [("2026-08", "skill_aim", 70.0), ("2026-09", "skill_aim", 40.0), ("2026-09", "skill_reference_stars", 5.0)],
        )
    m = progress.monthly(conn, "P").set_index("month")
    assert m.loc["2026-08", "skill_aim"] != m.loc["2026-08", "skill_aim"]  # NaN: the old scale
    assert m.loc["2026-09", "skill_aim"] == 40.0 and m.loc["2026-09", "skill_reference_stars"] == 5.0


def test_skills_need_a_few_plays_in_a_month(tmp_path, nm):
    few = [_copy(nm, f"f{i}", dt.datetime(2026, 8, 10 + i)) for i in range(2)]
    enough = [_copy(nm, f"n{i}", dt.datetime(2026, 9, 10 + i), miss_share=0.05, seed=i) for i in range(5)]
    conn = progress.connect(tmp_path)
    progress.record(conn, few + enough, UTC)
    progress.rebuild_months(conn, "Mot1one", few + enough, UTC)
    m = progress.monthly(conn, "Mot1one").set_index("month")
    assert m.loc["2026-08", "skill_aim"] != m.loc["2026-08", "skill_aim"]  # NaN: 2 plays say little
    assert m.loc["2026-09", "skill_aim"] == m.loc["2026-09", "skill_aim"]
    assert m.loc["2026-08", "comfort_stars"] > 0  # stars are still shown


def _plays_folder(tmp_path):
    folder = tmp_path / "plays"
    folder.mkdir()
    for n in MINE:
        rp, mp, _ = replay_and_map(n)
        shutil.copy(rp, folder / n)
        shutil.copy(mp, folder / f"{n}.osu")
    return folder


def test_update_uses_earlier_analyses_from_the_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(domain_progress, "FEW_PLAYS", 3)  # the three fixture plays make one "full" month
    lib = Library(tmp_path / "cache")
    lib.add_folder(_plays_folder(tmp_path))
    analyses, _ = lib.analyze(lib.eligible("Mot1one"), workers=1)
    assert len(analyses) == 3
    progress.update(lib.cache, analyses, lib.load_cached, UTC)  # first run: everything
    conn = progress.connect(lib.cache)
    before = progress.monthly(conn, "Mot1one")
    newest = max(analyses, key=lambda a: a.meta["date"])
    progress.update(lib.cache, [newest], lib.load_cached, UTC)  # later run: only the newest replay
    after = progress.monthly(progress.connect(lib.cache), "Mot1one")
    pd.testing.assert_frame_equal(before, after)
    assert before["plays"].sum() == 3 and before["ur_single"].notna().any()


# ------------------------------------------------------------------ command line and app
def test_cli_saves_progress_and_prints_it(tmp_path, capsys):
    cache = str(tmp_path / "cache")
    assert (
        main(
            [
                "analyze",
                "--no-auto",
                "--offline",
                "--folder",
                str(_plays_folder(tmp_path)),
                "--workers",
                "1",
                "-q",
                "--cache",
                cache,
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["progress", "--cache", cache]) == 0
    out = capsys.readouterr().out
    assert "Mot1one" in out and "2026-09" in out and "comfort" in out.lower()


def test_rolling_day_scores_rate_the_plays_of_the_last_7_days(tmp_path, nm):
    """One play a day says little; the goals chart follows the score of the last week's plays on each day (#70)."""
    early, late = _months(nm)  # one play a day: Aug 10-14 and Sep 10-14
    conn = progress.connect(tmp_path)
    progress.record(conn, early + late, UTC)
    progress.rebuild_months(conn, "Mot1one", early + late, UTC)
    months = progress.monthly(conn, "Mot1one").set_index("month")
    days = progress.by_period(conn, "Mot1one", "day", tz=UTC).set_index("month")
    rolling = progress.by_period(conn, "Mot1one", "day", tz=UTC, rolling=True).set_index("month")
    assert days["skill_aim"].isna().all()  # a single play a day: too few for a score of its own
    assert rolling.loc["2026-08-12", "skill_aim"] != rolling.loc["2026-08-12", "skill_aim"]  # 3 plays so far: too few
    # Aug 14 looks back to Aug 8: all five August plays, so the same score as the month
    assert rolling.loc["2026-08-14", "skill_aim"] == months.loc["2026-08", "skill_aim"]
    assert rolling.loc["2026-09-14", "skill_aim"] == months.loc["2026-09", "skill_aim"]
    assert (rolling["plays"] == days["plays"]).all()  # only the skills roll; the rest is still the day's


def test_rolling_falls_back_to_day_scores_saved_before_it_existed(tmp_path):
    conn = _two_months(tmp_path)
    with conn:
        conn.executemany(
            "INSERT INTO month_metrics VALUES ('P', ?, ?, ?, 0, '')",
            [("day:2026-09-05", "skill_aim", 40.0), ("day:2026-09-05", "skill_reference_stars", 5.0)],
        )
    rolling = progress.by_period(conn, "P", "day", tz=UTC, rolling=True).set_index("month")
    assert rolling.loc["2026-09-05", "skill_aim"] == 40.0
