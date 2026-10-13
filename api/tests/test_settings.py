"""Remembered choices and the player's setup (shared with the command line through settings.json)."""
from conftest import workspace

from osu_coach.library import load_settings, save_settings


def test_defaults(client):
    s = client.get("/api/settings").json()
    assert s["latest"] == 500 and s["date_range"] == "all" and s["replay_set"] == "all"
    assert s["level_override"] is None and s["source_mode"] == "library" and s["manual_comfort"] == 2.5


def test_patch_changes_only_the_given_fields(client):
    cache = workspace(client).cache_dir
    save_settings({"goals": [{"id": "x"}], "device": "mouse"}, cache)
    r = client.patch("/api/settings", json={"latest": 1000, "date_range": "custom", "date_from": "2026-09-01",
                                            "date_to": "2026-09-30", "level_override": 5.5})
    assert r.status_code == 200
    s = r.json()
    assert (s["latest"], s["date_range"], s["date_from"], s["date_to"], s["level_override"]) == \
        (1000, "custom", "2026-09-01", "2026-09-30", 5.5)
    saved = load_settings(cache)
    assert saved["goals"] == [{"id": "x"}] and saved["device"] == "mouse"        # untouched
    assert saved["date_from"] == "2026-09-01"                                    # ISO, as the CLI reads it


def test_null_clears_only_what_can_be_empty(client):
    client.patch("/api/settings", json={"level_override": 4.0, "latest": 100})
    s = client.patch("/api/settings", json={"level_override": None, "latest": None}).json()
    assert s["level_override"] is None and s["latest"] == 100


def test_level_override_range(client):
    assert client.patch("/api/settings", json={"level_override": 0.5}).status_code == 422
    assert client.patch("/api/settings", json={"level_override": 12.5}).status_code == 422


def test_values_the_app_doesnt_know_fall_back_to_defaults(client):
    save_settings({"latest": 42, "date_range": "forever", "date_from": "not a date", "player": "Mot1one"},
                  workspace(client).cache_dir)
    s = client.get("/api/settings").json()
    assert (s["latest"], s["date_range"], s["date_from"], s["player"]) == (500, "all", None, "Mot1one")


def test_setup_defaults(client):
    s = client.get("/api/setup").json()
    assert s["device"] == "tablet" and s["keyboard"] == "standard" and s["client"] == "stable"
    assert s["screen_w_px"] == 1920 and s["area_w_mm"] is None


def test_setup_saves_sayo_settings_and_area_position(client):
    setup = client.get("/api/setup").json()
    setup.update(keyboard="sayo", sayo_rt_trigger_mm=0.1, sayo_rt_lower_mm=3.8, area_x_mm=76.0, area_y_mm=47.0,
                 sayo_rt=True)
    r = client.put("/api/setup", json=setup)
    assert r.status_code == 200, r.text
    saved = load_settings(workspace(client).cache_dir)
    assert saved["keyboard"] == "sayo" and saved["sayo_rt_trigger_mm"] == 0.1 and saved["sayo_rt_lower_mm"] == 3.8
    assert saved["sayo_trigger_mm"] is None and saved["sayo_rt"] is True        # left empty / default on
    assert (saved["area_x_mm"], saved["area_y_mm"]) == (76.0, 47.0)
    assert saved["setup_saved"] is True
    assert client.get("/api/settings").json()["setup_saved"] is True


def test_setup_zero_means_unknown_and_ranges_are_checked(client):
    setup = client.get("/api/setup").json()
    r = client.put("/api/setup", json={**setup, "area_w_mm": 0, "mouse_dpi": 0})
    assert r.status_code == 200 and r.json()["area_w_mm"] is None and r.json()["mouse_dpi"] is None
    assert client.put("/api/setup", json={**setup, "screen_w_px": 100}).status_code == 422
    assert client.put("/api/setup", json={**setup, "device": "joystick"}).status_code == 422
    assert client.put("/api/setup", json={**setup, "colour": "pink"}).status_code == 422
