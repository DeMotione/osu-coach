import dataclasses
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import osu_coach
from osu_coach.analysis import analyze_files
from osu_coach.library import load_settings, save_settings
from osu_coach.profile import build_profile
from tests.conftest import replay_and_map

APP = str(Path(osu_coach.__file__).parent / "webapp" / "app.py")
PAGES = ["Replays", "Overview", "Progress", "Aim", "Tapping", "Sliders & reading", "Tips & setup",
         "Map suggestions", "Improve a skill"]


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


REG = {"n": 500, "scale_x": 1.0, "scale_y": 1.0, "rotation_deg": 0.0, "offset_x": 8.0, "offset_y": -4.0,
       "offset_se": 0.2, "residual_px": 15.0, "radius": 36.5}
SAYO = {"keyboard": "sayo", "sayo_stroke_mm": 4.0, "sayo_trigger_mm": 0.4, "sayo_release_mm": 0.35, "sayo_rt": True,
        "sayo_rt_trigger_mm": 0.1, "sayo_rt_release_mm": 0.15, "sayo_full_stroke": False, "sayo_rt_upper_mm": 0.1,
        "sayo_rt_lower_mm": 3.8}


def _tips_page(prof, tmp_path, monkeypatch, **sett):
    monkeypatch.setenv("OSU_COACH_CACHE", str(tmp_path))
    if sett:
        save_settings({"setup_saved": True, **sett}, tmp_path)
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["profile"] = dataclasses.replace(prof, regression=REG)
    at.session_state["page"] = "Tips & setup"
    return at.run()


def test_tips_page_shows_tablet_area_and_sayo_settings(prof, tmp_path, monkeypatch):
    at = _tips_page(prof, tmp_path, monkeypatch, device="tablet", area_w_mm=100.0, area_h_mm=56.25, area_x_mm=76.0,
                    area_y_mm=47.0, **SAYO)
    assert not at.exception, [e.value for e in at.exception]
    tables = [d.value for d in at.dataframe]
    area = next(t for t in tables if "Try (mm)" in t.columns)
    assert list(area["Now (mm)"]) == ["100", "56.25", "76", "47"] and area["Try (mm)"][2] != "76"
    sayo = next(t for t in tables if "Setting" in t.columns)
    assert "RT Lower Bound" in set(sayo["Setting"]) and set(sayo["Now"]) >= {"0.40 mm", "3.80 mm", "on"}


def test_setup_saves_sayo_settings_and_area_position(prof, tmp_path, monkeypatch):
    at = _tips_page(prof, tmp_path, monkeypatch)
    next(r for r in at.radio if r.label == "Keys").set_value("sayo").run()
    for label, v in (("RT Trigger (mm)", 0.1), ("RT Lower Bound (mm)", 3.8), ("Area X (mm)", 76.0),
                     ("Area Y (mm)", 47.0)):
        next(n for n in at.number_input if n.label == label).set_value(v)
    next(b for b in at.button if b.label == "Save setup").click().run()
    assert not at.exception, [e.value for e in at.exception]
    saved = load_settings(tmp_path)
    assert saved["keyboard"] == "sayo" and saved["sayo_rt_trigger_mm"] == 0.1 and saved["sayo_rt_lower_mm"] == 3.8
    assert saved["sayo_trigger_mm"] is None and saved["sayo_rt"] is True        # left empty / default on
    assert (saved["area_x_mm"], saved["area_y_mm"]) == (76.0, 47.0)
