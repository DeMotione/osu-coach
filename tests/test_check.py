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


def _play(key, date, misses, rate=1.0, ar=9.0, od=8.0, hp=5.0, mods="", acc=0.95):
    p = _fake(key, date, md5="m" * 32, stars=5.5, misses=misses)
    p.meta.update(rate=rate, ar=ar, od=od, hp=hp, mod_string=mods, accuracy=acc, source_path=f"C:/r/{key}.osr")
    return p


def test_compare_only_judges_plays_with_the_same_settings(tmp_path):
    """A DT ×1.5 play (faster, higher AR/OD) and a ×1.26 play of the same map are listed, but best / not best
    is only judged against plays with the same speed and settings."""
    conn = progress.connect(tmp_path)
    nm1 = _play("nm1", dt.datetime(2026, 9, 1), 6)
    nm2 = _play("nm2", dt.datetime(2026, 9, 2), 2)
    dt15 = _play("dt", dt.datetime(2026, 9, 3), 0, rate=1.5, ar=10.33, od=9.44, mods="DT")
    progress.record(conn, [nm1, nm2, dt15], UTC)
    custom = _play("x126", dt.datetime(2026, 9, 4), 1, rate=1.26, ar=9.9, od=9.0, mods="DT")   # file only, not saved
    now = _play("now", dt.datetime(2026, 10, 1), 1)
    c = check.compare(conn, now, [custom])
    assert (c["map_plays"], c["map_plays_all"], c["other_settings"]) == (2, 4, 2)
    assert (c["map_best_misses"], c["map_best"]) == (2, True)
    plays = c["plays"]
    assert list(plays["key"]) == ["now", "x126", "dt", "nm2", "nm1"]                  # newest first
    assert plays["this"].sum() == 1 and set(plays.loc[plays["same_settings"], "key"]) == {"now", "nm1", "nm2"}
    assert plays.set_index("key").loc["nm1", "path"] == "C:/r/nm1.osr"               # can be opened again
    # the DT play is compared with the DT play only
    now_dt = _play("now_dt", dt.datetime(2026, 10, 2), 3, rate=1.5, ar=10.33, od=9.44, mods="DT")
    c = check.compare(conn, now_dt, [custom])
    assert (c["map_plays"], c["map_best_misses"], c["map_best"]) == (1, 0, False)
    assert c["settings"] == "×1.5 · AR 10.3 · OD 9.4 · CS 4 · HP 5"


def test_plays_saved_without_hp_still_match(tmp_path):
    conn = progress.connect(tmp_path)
    old = _play("old", dt.datetime(2026, 9, 1), 3)
    old.meta["hp"] = None                                          # saved by a version that didn't keep HP
    progress.record(conn, [old], UTC)
    c = check.compare(conn, _play("now", dt.datetime(2026, 10, 1), 1))
    assert c["map_plays"] == 1 and c["map_best"]


def test_compare_without_history(tmp_path):
    c = check.compare(progress.connect(tmp_path), _fake("now", dt.datetime(2026, 10, 1)))
    assert c["map_plays"] == 0 and c["map_plays_all"] == 0 and len(c["plays"]) == 1


def test_mods_label_spells_out_custom_speeds():
    assert check.mods_label("DT", 1.5) == "DT" and check.mods_label("HDDT", 1.26) == "HDDT ×1.26"
    assert check.mods_label("", 1.0) == "NM" and check.mods_label("", 0.85) == "NM ×0.85"


def test_old_progress_databases_get_the_new_columns(tmp_path):
    import sqlite3
    db = sqlite3.connect(tmp_path / progress.DB_FILE)
    db.execute("CREATE TABLE replays (key TEXT PRIMARY KEY, played_at TEXT, month TEXT NOT NULL, added_at TEXT, "
               "player TEXT, beatmap_md5 TEXT)")
    db.commit()
    db.close()
    conn = progress.connect(tmp_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(replays)")}
    assert {"hp", "path", "ur", "rate"} <= cols
    progress.record(conn, [_play("k", dt.datetime(2026, 9, 1), 0)], UTC)
    assert conn.execute("SELECT hp, path FROM replays").fetchone() == (5.0, "C:/r/k.osr")


def test_practice_sections_cover_the_misses_and_snap_to_notes(legit):
    ev = check.events(legit)
    secs = check.practice_sections(legit, ev)
    assert secs
    times = set(legit.objects["time"])
    ends = set(legit.objects["end_time"].fillna(legit.objects["time"]))
    rate = legit.meta.get("rate") or 1.0
    for x in secs:
        assert x["start"] <= x["first_event"] and x["end"] >= x["last_event"]
        assert x["start"] in times and x["end"] in ends                               # whole notes
        assert x["seconds"] == pytest.approx((x["end"] - x["start"]) / 1000 / rate)
        inside = legit.objects[(legit.objects["time"] >= x["start"]) & (legit.objects["time"] <= x["end"])]
        assert x["notes"] == len(inside)
        assert x["first_event"] - x["start"] <= 4 * legit.objects["beat_len"].max() + 1   # about a measure before


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
    assert "Detailed map analysis — Mot1one" in out and _title("mot1one__lazer_failed.osr") in out   # played last
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
    at.session_state["page"] = "Detailed Map Analysis"
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
    assert any(s.value == "All your plays of this map" for s in at.subheader)
    labels = {m.label for m in at.metric}
    assert {"BPM", "UR", "Speed", "AR", "OD", "CS", "HP", "Length"} <= labels
    assert next(t for t in at.toggle if t.label == "Only plays of this map").value is False   # nothing opened yet
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
    # opened from the Replays page: the list shows that map's plays only (here: this one play)
    assert next(t for t in at.toggle if t.label == "Only plays of this map").value is True
    assert len(next(s for s in at.selectbox if s.label == "Replay").options) == 1


def test_check_page_without_replays_says_what_to_do(tmp_path, monkeypatch):
    at = _page(tmp_path, monkeypatch)
    assert not at.exception and at.info
