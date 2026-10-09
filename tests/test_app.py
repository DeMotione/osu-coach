import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import osu_coach
from osu_coach.analysis import analyze_files
from osu_coach.profile import build_profile
from tests.conftest import replay_and_map

APP = str(Path(osu_coach.__file__).parent / "webapp" / "app.py")
PAGES = ["Replays", "Overview", "Aim", "Tapping", "Sliders & reading", "Tips & setup", "Map suggestions",
         "Improve a skill"]


@pytest.fixture(scope="module")
def prof():
    names = ["circlecore__legit__legit-12.osr", "osrparse__resources__replay.osr"]
    return build_profile([analyze_files(*replay_and_map(n)[:2]) for n in names])


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_with_a_profile(page, prof, tmp_path, monkeypatch):
    monkeypatch.setenv("OSU_COACH_CACHE", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["profile"] = prof
    at.session_state["page"] = page
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.title and at.title[0].value


@pytest.mark.parametrize("page", ["Overview", "Improve a skill"])
def test_pages_without_replays_explain_what_to_do(page, tmp_path, monkeypatch):
    monkeypatch.setenv("OSU_COACH_CACHE", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["page"] = page
    at.run()
    assert not at.exception
    assert at.info  # "analyse your replays first" / manual level


def test_scan_and_analyse_a_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("OSU_COACH_CACHE", str(tmp_path / "cache"))
    folder = tmp_path / "plays"
    folder.mkdir()
    rp, mp, _ = replay_and_map("circlecore__low_frametime_old__replay-osu_24722_433541214.osr")
    shutil.copy(rp, folder / "a.osr")
    shutil.copy(mp, folder / "a.osu")
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    at.text_area[0].set_value(str(folder)).run()
    next(b for b in at.button if b.label == "Scan").click().run()
    assert not at.exception, [e.value for e in at.exception]
    next(b for b in at.button if b.label == "Analyse replays").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["profile"].overview["replays"] == 1
    assert any("Analysed 1 replays" in s.value for s in at.success)
