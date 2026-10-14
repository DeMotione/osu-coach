"""The analysis pages."""
import copy
import dataclasses

import numpy as np
import pandas as pd
import pytest
from tests.conftest import sample_paths, workspace

from osu_coach.library.repository import analyze_files
from osu_coach.settings.repository import load_settings, save_settings
from osu_coach.profile.domain import SKILL_LABELS, build_profile, stream_fall_behind, stream_speed_profile


pytestmark = pytest.mark.usefixtures("_isolated")

PAGES = ["summary", "replays", "overview", "aim", "clicks", "tapping", "sliders-reading", "tips"]


@pytest.mark.parametrize("page", PAGES)
def test_pages_before_anything_was_analysed_say_what_to_do(client, page):
    r = client.get(f"/api/profile/{page}")
    assert r.status_code == 409
    assert r.json()["code"] == "no_profile" and "Analyse replays" in r.json()["detail"]


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_with_real_replays(analysed, page):
    r = analysed.get(f"/api/profile/{page}")
    assert r.status_code == 200, r.text
    assert r.json()


def test_replays_table_newest_first_with_weights(analysed):
    rows = analysed.get("/api/profile/replays").json()
    assert len(rows) == 3
    assert [r["played_at"] for r in rows] == sorted((r["played_at"] for r in rows), reverse=True)
    assert all(r["played_at"].endswith("Z") for r in rows)
    assert all(0 < r["weight"] <= 1 and r["path"].endswith(".osr") for r in rows)


def test_overview_explains_every_skill(analysed):
    """Each skill comes with its score (or why there is none) and the player's own numbers behind it."""
    ov = analysed.get("/api/profile/overview").json()
    assert [s["key"] for s in ov["skills"]] == list(SKILL_LABELS)
    for s in ov["skills"]:
        assert s["label"] == SKILL_LABELS[s["key"]] and s["facts"]
        if s["score"] is None:
            assert s["score_text"] in ("not enough data", "too few misses to tell")
        else:
            assert s["score_text"].startswith(f"{s['score']:.0f}")
    assert len(ov["top"]) == len(SKILL_LABELS)
    first = ov["level"]["weights"][0]                         # README: "1★ off 61%"
    assert ov["level"]["stars"] is not None and first["stars_off"] == 1 and first["weight"] == pytest.approx(0.61, abs=0.01)
    assert ov["kpis"]["replays"] == 3 and 0 < ov["kpis"]["accuracy"] <= 1
    shares = sum(c["share"] for c in ov["miss_causes"])
    assert shares == pytest.approx(1.0) if ov["miss_causes"] else shares == 0
    assert len(ov["top_tips"]) <= 3 and not any(t["title"].endswith("fits") for t in ov["top_tips"])


def test_aim_page_shapes(analysed):
    aim = analysed.get("/api/profile/aim").json()
    assert [q["quadrant"] for q in aim["quadrants"]] == ["top-left", "top-right", "bottom-left", "bottom-right"]
    assert len(aim["grid"]["rate"]) == 6 and all(len(row) == 8 for row in aim["grid"]["rate"])
    assert len(aim["directions"]) == 8 and {d["angle"] for d in aim["directions"]} == set(range(0, 360, 45))
    assert aim["distances"] and aim["angles"]


@pytest.mark.parametrize("view", ["screen", "movement"])
def test_clicks(analysed, view):
    c = analysed.get("/api/profile/clicks", params={"view": view}).json()
    assert c["view"] == view and c["enough"]
    assert len(c["x"]) == len(c["y"]) == len(c["hit"]) == c["drawn"] <= c["n"]
    assert max(abs(v) for v in c["x"] + c["y"]) < 2.4
    assert [b["label"] for b in c["summary"]["bands"]][-1] == "outside"
    assert analysed.get("/api/profile/clicks", params={"view": "sideways"}).status_code == 422


def test_tapping_and_sliders_pages(analysed):
    t = analysed.get("/api/profile/tapping").json()
    assert len(t["timing"]["centers"]) == len(t["timing"]["n300"]) == 100
    assert t["keys"]["shares"] and t["kpis"]["ur"] > 0
    s = analysed.get("/api/profile/sliders-reading").json()
    assert s["kpis"]["sliders"] > 0
    for row in s["hits_by_ar"]:
        assert row["r300"] + row["r100"] + row["r50"] + row["miss"] == pytest.approx(100)


# ------------------------------------------------------------------ choices that rebuild the profile
def _two_plays_of_one_map():
    rp, mp = sample_paths("circlecore__legit__legit-12.osr")
    a = analyze_files(rp, mp)
    b = copy.deepcopy(a)
    b.key = b.meta["key"] = "retry"
    b.meta["score"] = a.meta["score"] + 1000            # the better play of the same map and speed ...
    c = copy.deepcopy(a)
    c.key = c.meta["key"] = "failed"
    c.meta.update(score=a.meta["score"] * 10, completed=False)   # ... a failed one never counts as best
    return [a, b, c]


def test_best_replays_switch_rebuilds_the_profile(client):
    workspace(client).set_analyses(_two_plays_of_one_map(), [], "tester")
    assert client.get("/api/profile/summary").json()["replays"] == 3
    client.patch("/api/settings", json={"replay_set": "best"})
    summary = client.get("/api/profile/summary").json()
    assert summary["replays"] == 1 and summary["replay_set"] == "best"
    assert [r["key"] for r in client.get("/api/profile/replays").json()] == ["retry"]


def test_level_override_is_used_and_remembered(client):
    workspace(client).set_analyses(_two_plays_of_one_map(), [], "tester")
    client.patch("/api/settings", json={"level_override": 3.0})
    assert load_settings(workspace(client).cache_dir)["level_override"] == 3.0
    lv = client.get("/api/profile/overview").json()["level"]
    assert lv["stars"] == 3.0 and lv["override"]
    client.patch("/api/settings", json={"level_override": None})
    assert client.get("/api/profile/overview").json()["level"]["override"] is False


# ------------------------------------------------------------------ tips & setup
REG = {"n": 500, "scale_x": 1.0, "scale_y": 1.0, "rotation_deg": 0.0, "offset_x": 8.0, "offset_y": -4.0,
       "offset_se": 0.2, "residual_px": 15.0, "radius": 36.5}
SAYO = {"keyboard": "sayo", "sayo_stroke_mm": 4.0, "sayo_trigger_mm": 0.4, "sayo_release_mm": 0.35, "sayo_rt": True,
        "sayo_rt_trigger_mm": 0.1, "sayo_rt_release_mm": 0.15, "sayo_full_stroke": False, "sayo_rt_upper_mm": 0.1,
        "sayo_rt_lower_mm": 3.8}


@pytest.fixture(scope="module")
def small_profile():
    names = ["circlecore__legit__legit-12.osr", "osrparse__resources__replay.osr"]
    return build_profile([analyze_files(*sample_paths(n)) for n in names])


def _with_profile(client, monkeypatch, prof):
    ws = workspace(client)
    monkeypatch.setattr(ws, "profile", lambda: prof)
    return ws


def test_tips_page_shows_tablet_area_and_sayo_settings(client, monkeypatch, small_profile):
    ws = _with_profile(client, monkeypatch, dataclasses.replace(small_profile, regression=REG))
    save_settings({"setup_saved": True, "device": "tablet", "area_w_mm": 100.0, "area_h_mm": 56.25, "area_x_mm": 76.0,
                   "area_y_mm": 47.0, **SAYO}, ws.cache_dir)
    page = client.get("/api/profile/tips").json()
    area = page["tablet_area"]
    assert (area["now_w"], area["now_h"], area["now_x"], area["now_y"]) == (100, 56.25, 76, 47)
    assert area["x"] != 76                                         # the 8 px offset moves the area
    sayo = next(t for t in page["tips"] if t["category"] == "Keys / SayoDevice")["sayo"]
    rows = {r["setting"]: r for r in sayo}
    assert "RT Lower Bound" in rows and rows["Trigger"]["now"] == 0.4 and rows["RT Mode"]["now"] is True
    assert page["calibration"]["lines"] and page["setup"]["keyboard"] == "sayo" and page["setup_saved"]
    assert page["practice_plan"]


def test_tip_settings_are_listed_as_text(client, monkeypatch, small_profile):
    _with_profile(client, monkeypatch, dataclasses.replace(small_profile, regression={**REG, "rotation_deg": 9.0}))
    tips = client.get("/api/profile/tips").json()["tips"]
    rotation = next(t for t in tips if "rotated" in t["title"])
    assert {"name": "rotation_deg", "value": "9.0"} in rotation["settings"]


def _long_streams(n_runs, length, err_fn, seed=3, bpm=200.0):
    """Long streams whose timing error grows by ``err_fn(pos)`` (as in the core tests)."""
    rng = np.random.default_rng(seed)
    rows = []
    for run in range(n_runs):
        for pos in range(length):
            size = err_fn(pos) + abs(rng.normal(0, 1))
            rows.append({"run_len": length, "run_pos": pos, "run_id": run, "replay_key": "r", "head_hit": True,
                         "err_real": size * (1 if rng.random() < 0.5 else -1), "stream_bpm": bpm, "played": True,
                         "kind": "circle"})
    return pd.DataFrame(rows)


def _plays_at(bpm, ur, offsets, n=60, seed=0):
    """``len(offsets)`` plays at one stream speed, each with UR ``ur`` around its own average (as in the core tests)."""
    rng = np.random.default_rng(seed)
    rows = []
    for k, off in enumerate(offsets):
        e = rng.normal(0, 1, n)
        e = (e - e.mean()) / e.std() * ur / 10 + off
        rows += [{"run_len": 20, "run_pos": 1 + i % 19, "stream_bpm": bpm + 2, "head_hit": True, "miss_reason": None,
                  "err_real": float(x), "played": True, "kind": "circle", "head_result": 300, "pattern": "stream",
                  "replay_key": f"{bpm}-{k}"} for i, x in enumerate(e)]
    return rows


def test_tapping_page_shows_stream_stamina_and_weak_speeds(client, monkeypatch, small_profile):
    """Precision through long streams, the comfortable stream length with maps to practise, and the stream-speed
    UR with its trend and weak speeds."""
    fb = stream_fall_behind(_long_streams(80, 48, lambda pos: 10.0 if pos < 20 else 10.0 + 1.5 * (pos - 20)))
    rows = []
    for i, bpm in enumerate(range(180, 270, 10)):
        rows += _plays_at(bpm, 100 + 2 * (bpm - 180) + (150 if bpm == 200 else 0), [0, 5, -5], seed=i)
    sp = stream_speed_profile(pd.DataFrame(rows))
    _with_profile(client, monkeypatch, dataclasses.replace(small_profile, fall_behind=fb, stream_profile=sp))
    t = client.get("/api/profile/tapping").json()
    f = t["fall_behind"]
    assert f["available"] and f["start_note"] == fb["start_note"] and f["comfort_notes"] == fb["comfort_notes"]
    assert f["practice_notes"] == list(fb["practice_notes"])
    assert f["comfortable_maps"]["maps"] and f["practice_maps"]["maps"]          # the two map lists
    assert f["practice_maps"]["min_notes"] == fb["practice_notes"][0]
    weak = [r["bpm"] for r in t["stream_speed"]["rows"] if r["weak"]]
    assert weak == [200]
