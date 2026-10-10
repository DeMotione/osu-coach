"""Single replay check: one play on its own — misses and combo breaks with osu! editor timestamps, where
they cluster, timing, and how the play compares with your other plays."""
import datetime as dt
import shutil

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from osu_coach import check, progress
from osu_coach.analysis import analyze_files
from osu_coach.beatmap import read_metadata
from osu_coach.cli import main
from osu_coach.library import Library
from tests.conftest import replay_and_map
from tests.test_app import APP
from tests.test_progress import MINE, _fake

UTC = dt.timezone.utc


@pytest.fixture(scope="module")
def legit():   # an osu!stable play with every kind of miss and some slider breaks
    return analyze_files(*replay_and_map("circlecore__legit__legit-12.osr")[:2])


@pytest.fixture(scope="module")
def nm():      # one of Nikita's lazer plays: 2 aim misses
    return analyze_files(*replay_and_map("mot1one__lazer_nm.osr")[:2])


def _title(name):
    return read_metadata(replay_and_map(name)[1])["Title"]


# ------------------------------------------------------------------ the check itself
def test_timestamps_use_the_osu_editor_format():
    assert check.timestamp(83456) == "01:23:456"
    assert check.timestamp(5.4) == "00:00:005"
    assert check.timestamp(3_723_004) == "62:03:004"


def test_map_title_is_read_without_parsing_the_whole_map():
    md = read_metadata(replay_and_map("mot1one__lazer_nm.osr")[1])
    assert md["Artist"] and md["Title"] and md["Version"]
    assert check.map_label(md) == f"{md['Artist']} – {md['Title']} [{md['Version']}]"
    assert check.map_label({}) == "(map not on this computer)"


def test_events_are_the_misses_and_combo_breaks_of_the_play(legit):
    ev = check.events(legit)
    assert (ev["what"] == "miss").sum() == legit.meta["sim_counts"][3]      # the results screen's misses
    assert (ev["what"] == "slider break").sum() == 6
    assert list(ev["time"]) == sorted(ev["time"])
    assert ev["timestamp"].str.fullmatch(r"\d\d:\d\d:\d\d\d").all()
    aim = ev[ev["reason"] == "aim"]
    assert len(aim) and aim["detail"].str.contains("radii").all()
    assert set(ev["reason"]) >= {"aim", "notelock", "no_tap", "follow"}


def test_lazer_play_events(nm):
    ev = check.events(nm)
    assert list(ev["what"]) == ["miss", "miss"] and set(ev["reason"]) == {"aim"}


def test_sections_group_misses_close_in_time():
    ev = pd.DataFrame({"time": [1000, 2000, 2500, 9000, 20000, 20500],
                       "what": ["miss"] * 5 + ["slider break"],
                       "reason": ["aim", "aim", "no_tap", "aim", "aim", "follow"],
                       "pattern": ["stream", "stream", "stream", "jump", "jump", "slider"],
                       "stream_bpm": [220, 220, 220, None, None, None]})
    s = check.sections(ev, gap_ms=3000)
    assert [(x["start"], x["end"], x["count"]) for x in s] == [(1000, 2500, 3), (20000, 20500, 2), (9000, 9000, 1)]
    assert s[0]["reasons"] == {"aim": 2, "no_tap": 1} and s[0]["pattern"] == "stream" and s[0]["bpm"] == 220


def test_summary_says_what_cost_the_play(nm, legit):
    s = check.summary(nm)
    assert (s["misses"], s["slider_breaks"]) == (2, 0)
    assert s["accuracy"] == pytest.approx(nm.meta["accuracy"]) and s["sim_exact"] is True
    assert "2 misses" in s["verdict"][0] and "aim" in s["verdict"][0]
    s = check.summary(legit)
    assert s["slider_breaks"] == 6 and s["misses"] == legit.meta["sim_counts"][3]
    assert any("Timing" in v for v in s["verdict"])


def test_compare_with_the_same_map_and_similar_difficulty(tmp_path):
    conn = progress.connect(tmp_path)
    md5 = "m" * 32
    older = [_fake("p1", dt.datetime(2026, 9, 1), md5=md5, stars=5.5, misses=6),
             _fake("p2", dt.datetime(2026, 9, 2), md5=md5, stars=5.5, misses=2)]
    others = [_fake(f"o{i}", dt.datetime(2026, 9, 3 + i), md5=f"{i:032d}", stars=5.2 + i * 0.1, misses=i)
              for i in range(6)]
    progress.record(conn, older + others + [_fake("far", dt.datetime(2026, 9, 20), md5="f" * 32, stars=8.0)], UTC)
    now = _fake("now", dt.datetime(2026, 10, 1), md5=md5, stars=5.5, misses=1)
    c = check.compare(conn, now)
    assert (c["map_plays"], c["map_best_misses"], c["map_best"]) == (2, 2, True)
    assert c["similar_n"] == 8                       # ±0.5★, without the 8★ play
    assert c["misses_better_than"] == pytest.approx(0.75)
    progress.record(conn, [now], UTC)                # the play itself never counts as "before"
    assert check.compare(conn, now)["map_plays"] == 2


def test_compare_without_history(tmp_path):
    c = check.compare(progress.connect(tmp_path), _fake("now", dt.datetime(2026, 10, 1)))
    assert c["map_plays"] == 0 and c["similar_n"] == 0


# ------------------------------------------------------------------ command line and app
def _plays(tmp_path):
    folder = tmp_path / "plays"
    folder.mkdir()
    for n in MINE:
        rp, mp, _ = replay_and_map(n)
        shutil.copy(rp, folder / n)
        shutil.copy(mp, folder / f"{n}.osu")
    return folder


def test_cli_checks_the_newest_replay(tmp_path, capsys):
    folder = _plays(tmp_path)
    assert main(["check", "--no-auto", "--offline", "--folder", str(folder), "-q",
                 "--cache", str(tmp_path / "cache")]) == 0
    out = capsys.readouterr().out
    assert "Replay check — Mot1one" in out and _title("mot1one__lazer_failed.osr") in out   # played last
    assert "Misses and combo breaks" in out and "failed" in out.lower()


def test_cli_checks_a_given_replay(tmp_path, capsys):
    folder = _plays(tmp_path)
    assert main(["check", str(folder / "mot1one__lazer_nm.osr"), "--no-auto", "--offline", "--folder", str(folder),
                 "-q", "--cache", str(tmp_path / "cache")]) == 0
    out = capsys.readouterr().out
    assert _title("mot1one__lazer_nm.osr") in out and "2 misses" in out
    # the check is saved in the history like any analysis
    assert progress.players(progress.connect(tmp_path / "cache")) == [("Mot1one", 1)]


def _page(tmp_path, monkeypatch, **state):
    monkeypatch.setenv("OSU_COACH_CACHE", str(tmp_path / "cache"))
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["page"] = "Replay check"
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


def test_check_page_shows_the_newest_replay_and_others_on_request(tmp_path, monkeypatch):
    lib = Library(tmp_path / "cache")
    lib.add_folder(_plays(tmp_path))
    at = _page(tmp_path, monkeypatch, lib=lib)
    assert not at.exception, [e.value for e in at.exception]
    assert _title("mot1one__lazer_failed.osr") in at.subheader[0].value
    assert any(s.value == "Misses and combo breaks" for s in at.subheader)
    pick = next(s for s in at.selectbox if s.label == "Replay")
    pick.set_value(2).run()                          # the oldest of the three
    assert not at.exception, [e.value for e in at.exception]
    assert _title("mot1one__lazer_nm.osr") in at.subheader[0].value


def test_check_page_opens_the_replay_chosen_on_the_replays_page(tmp_path, monkeypatch):
    lib = Library(tmp_path / "cache")
    folder = _plays(tmp_path)
    lib.add_folder(folder)
    at = _page(tmp_path, monkeypatch, lib=lib, check_path=str(folder / "mot1one__lazer_dthd_spinner.osr"))
    assert not at.exception, [e.value for e in at.exception]
    assert _title("mot1one__lazer_dthd_spinner.osr") in at.subheader[0].value


def test_check_page_without_replays_says_what_to_do(tmp_path, monkeypatch):
    at = _page(tmp_path, monkeypatch)
    assert not at.exception and at.info
