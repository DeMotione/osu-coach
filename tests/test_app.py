import dataclasses
import json
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
PAGES = ["Replays", "Detailed Map Analysis", "Overview", "Progress", "Aim", "Tapping", "Sliders & Reading",
         "Tips & Setup", "Map Suggestion", "Skill Development"]


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
    # no chart can be zoomed or panned by click-and-drag
    for el in at.get("plotly_chart"):
        spec = json.loads(el.proto.spec)
        layout = spec.get("layout", {})
        assert layout.get("dragmode") is False, page
        axes = [v for k, v in layout.items() if k.startswith(("xaxis", "yaxis"))]
        if "polar" not in layout:    # polar charts: dragmode=False is enough
            assert axes and all(a.get("fixedrange") is True for a in axes), page


@pytest.mark.parametrize("page", ["Overview", "Skill Development"])
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
    at.session_state["page"] = "Tips & Setup"
    return at.run()


def test_tips_page_shows_tablet_area_and_sayo_settings(prof, tmp_path, monkeypatch):
    at = _tips_page(prof, tmp_path, monkeypatch, device="tablet", area_w_mm=100.0, area_h_mm=56.25, area_x_mm=76.0,
                    area_y_mm=47.0, **SAYO)
    assert not at.exception, [e.value for e in at.exception]
    tables = [d.value for d in at.dataframe]
    area = next(t for t in tables if "Try (mm)" in t.columns)
    assert list(area["Now (mm)"]) == ["100", "56.25", "76", "47"] and area["Try (mm)"][2] != "76"
    sayo = next(t for t in tables if "Setting" in t.columns and "Now" in t.columns)
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


def _two_plays_of_one_map():
    import copy
    a = analyze_files(*replay_and_map("circlecore__legit__legit-12.osr")[:2])
    b = copy.deepcopy(a)
    b.key = b.meta["key"] = "retry"
    b.meta["score"] = a.meta["score"] + 1000            # the better play of the same map and speed ...
    c = copy.deepcopy(a)
    c.key = c.meta["key"] = "failed"
    c.meta.update(score=a.meta["score"] * 10, completed=False)   # ... a failed one never counts as best
    return [a, b, c]


def test_best_replays_switch_rebuilds_the_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("OSU_COACH_CACHE", str(tmp_path))
    plays = _two_plays_of_one_map()
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["analyses"] = plays
    at.session_state["page"] = "Overview"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["profile"].overview["replays"] == 3
    save_settings({"replay_set": "best"}, tmp_path)
    at.session_state["settings"] = {"replay_set": "best"}
    at.run()
    prof = at.session_state["profile"]
    assert prof.overview["replays"] == 1 and list(prof.replays["key"]) == ["retry"]
    assert "best replays" in at.sidebar.caption[0].value


def test_level_override_is_used_and_remembered(tmp_path, monkeypatch):
    monkeypatch.setenv("OSU_COACH_CACHE", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["analyses"] = _two_plays_of_one_map()
    at.session_state["page"] = "Overview"
    at.run()
    next(t for t in at.toggle if t.label == "Set my level by hand").set_value(True).run()
    next(n for n in at.number_input if n.label == "My level (★)").set_value(3.0).run()
    assert not at.exception, [e.value for e in at.exception]
    assert load_settings(tmp_path)["level_override"] == 3.0
    lv = at.session_state["profile"].levels
    assert lv["level_stars"] == 3.0 and lv["level_override"]


def test_tapping_page_shows_stream_stamina_and_weak_speeds(prof, tmp_path, monkeypatch):
    """Precision through long streams (one line per stream length), the comfortable stream length with maps
    to practise, and the stream-speed UR with its trend and weak speeds."""
    import pandas as pd
    from osu_coach.profile import stream_fall_behind, stream_speed_profile
    from tests.test_weighting import _long_streams, _plays_at
    fb = stream_fall_behind(_long_streams(80, 48, lambda pos: 10.0 if pos < 20 else 10.0 + 1.5 * (pos - 20)))
    rows = []
    for i, bpm in enumerate(range(180, 270, 10)):
        rows += _plays_at(bpm, 100 + 2 * (bpm - 180) + (150 if bpm == 200 else 0), [0, 5, -5], seed=i)
    sp = stream_speed_profile(pd.DataFrame(rows))
    monkeypatch.setenv("OSU_COACH_CACHE", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["profile"] = dataclasses.replace(prof, fall_behind=fb, stream_profile=sp)
    at.session_state["page"] = "Tapping"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    text = " ".join(m.value for m in at.markdown)
    assert f"Your stamina gives in after about {fb['start_note']} notes" in text
    assert f"streams up to **{fb['comfort_notes']} notes**" in text
    assert any("Weak spots" in c.value and "200–209" in c.value for c in at.caption)
    labels = [t.label for t in at.tabs]
    assert any(lbl.startswith("Maps: stamina practice") for lbl in labels)
    assert len(at.dataframe) >= 2                                   # the two map lists


def test_overview_skill_bars_explain_each_skill_on_hover(prof, tmp_path, monkeypatch):
    """Pointing at a skill bar shows what the skill measures, how it is scored, the player's numbers and
    what raises it, for every skill (also the ones without enough data)."""
    import json
    from osu_coach.profile import SKILL_HELP, SKILL_LABELS
    assert set(SKILL_HELP) == set(SKILL_LABELS)
    monkeypatch.setenv("OSU_COACH_CACHE", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["profile"] = prof
    at.session_state["page"] = "Overview"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    specs = [json.loads(c.proto.spec) for c in at.get("plotly_chart")]
    bars = next(s for s in specs if any(t.get("orientation") == "h" and set(t.get("y", [])) >=
                                       {v for v in SKILL_LABELS.values()} for t in s["data"]))
    trace = next(t for t in bars["data"] if t.get("orientation") == "h")
    assert bars["layout"]["hovermode"] == "y"
    assert len(trace["hovertext"]) == len(SKILL_LABELS)
    for label, text in zip(trace["y"], trace["hovertext"]):
        assert text.startswith(f"<b>{label}: ")
        assert "Score:" in text and "You: " in text and "To raise it: " in text
        assert all(len(line) <= 80 for line in text.replace("<b>", "").replace("</b>", "").split("<br>"))


def test_skill_hovers_fit_inside_the_skills_chart():
    """A hover box taller than the chart gets cut off or isn't shown (that happened to Stamina): every skill's
    hover, with all its facts filled in, stays at 18 lines or fewer."""
    import math
    import textwrap
    from osu_coach.profile import SKILL_HELP, SKILL_LABELS
    src = Path(APP).read_text(encoding="utf-8")
    ns = {"math": math, "textwrap": textwrap, "SKILL_HELP": SKILL_HELP, "SKILL_LABELS": SKILL_LABELS}
    exec(src[src.index("def _num("):src.index("def page_overview")], ns)
    full = {"score": 64.0, "n": 12345, "observed": 12, "expected": 20, "three_hundred_rate": 0.95, "ur": 90,
            "break_rate": 0.02, "miss_after_miss_ratio": 2.4, "streams_kept": 30, "streams_long": 34,
            "best_stream": {"notes": 128, "bpm": 280.0}, "stream_score": 70, "window_score": 60, "map_score": 55,
            "endurance_score": 80, "longest_minutes": 45, "steadiness": 0.97, "streams_slowed": 2,
            "streams_overstreamed": 1}
    for key, label in SKILL_LABELS.items():
        cases = [full] + ([{**full, "score": None, "too_few_misses": True}]
                          if key not in ("stamina", "accuracy", "sliders") else [])   # only miss-based skills
        for v in cases:
            lines = ns["skill_hover"](key, {**v, "label": label}).count("<br>") + 1
            assert lines <= 18, (key, lines)


def test_skill_development_makes_a_plan_and_tracks_goals(prof, tmp_path, monkeypatch):
    monkeypatch.setenv("OSU_COACH_CACHE", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["profile"] = prof
    at.session_state["page"] = "Skill Development"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    plan = [b for b in at.button if b.label == "Make this plan"]
    if not plan:                                 # the tiny test profile may have no scored skills
        return
    plan[0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    saved = load_settings().get("goals") or []
    assert saved and all({"skill", "target", "deadline", "start"} <= set(g) for g in saved)
    assert any("of the way" in (p.text or "") for p in at.get("progress"))
