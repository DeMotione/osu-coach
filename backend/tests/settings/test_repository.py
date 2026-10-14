import json

import pytest

from osu_coach.settings.repository import load_settings, save_settings


def test_missing_file_loads_as_empty(tmp_path):
    assert load_settings(tmp_path) == {}


def test_missing_folder_loads_as_empty(tmp_path):
    assert load_settings(tmp_path / "nope") == {}


def test_round_trip(tmp_path):
    settings = {
        "latest": 500,
        "device": "mouse",
        "area_w_mm": 152.5,
        "sayo_rt": True,
        "level_override": None,
        "goals": [{"id": "x", "target": 0.9}],
    }
    save_settings(settings, tmp_path)
    assert load_settings(tmp_path) == settings


def test_unknown_keys_are_kept(tmp_path):
    save_settings({"from_a_newer_version": {"a": [1, 2]}}, tmp_path)
    assert load_settings(tmp_path)["from_a_newer_version"] == {"a": [1, 2]}


def test_save_creates_the_data_folder(tmp_path):
    folder = tmp_path / "a" / "b"
    save_settings({"latest": 1}, folder)
    assert (folder / "settings.json").is_file()


def test_save_replaces_the_previous_content(tmp_path):
    save_settings({"a": 1, "b": 2}, tmp_path)
    save_settings({"b": 3}, tmp_path)
    assert load_settings(tmp_path) == {"b": 3}


def test_file_is_readable_json_in_the_data_folder(tmp_path):
    save_settings({"player": "Mot1one"}, tmp_path)
    text = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert json.loads(text) == {"player": "Mot1one"}
    assert "\n" in text  # indented, for people editing it by hand


def test_non_ascii_text_round_trips(tmp_path):
    save_settings({"player": "ミクさん", "note": "ž"}, tmp_path)
    assert load_settings(tmp_path) == {"player": "ミクさん", "note": "ž"}


def test_str_and_path_folders_are_equivalent(tmp_path):
    save_settings({"latest": 7}, str(tmp_path))
    assert load_settings(tmp_path) == {"latest": 7}


@pytest.mark.parametrize("content", ["", "{", "not json", '{"a": 1,}', "\x00\x01"])
def test_corrupt_file_loads_as_empty(tmp_path, content):
    (tmp_path / "settings.json").write_text(content, encoding="utf-8")
    assert load_settings(tmp_path) == {}


def test_file_that_is_not_utf8_loads_as_empty(tmp_path):
    (tmp_path / "settings.json").write_bytes(b"\xff\xfe\x00{")
    assert load_settings(tmp_path) == {}


def test_a_folder_in_place_of_the_file_loads_as_empty(tmp_path):
    (tmp_path / "settings.json").mkdir()
    assert load_settings(tmp_path) == {}


def test_partial_file_returns_only_what_it_has(tmp_path):
    (tmp_path / "settings.json").write_text('{"latest": 42}', encoding="utf-8")
    assert load_settings(tmp_path) == {"latest": 42}  # defaults are applied by the callers


def test_corrupt_file_can_be_overwritten_by_a_save(tmp_path):
    (tmp_path / "settings.json").write_text("{", encoding="utf-8")
    save_settings({"latest": 3}, tmp_path)
    assert load_settings(tmp_path) == {"latest": 3}


def test_save_to_an_unwritable_place_raises(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(OSError):
        save_settings({"a": 1}, blocker / "sub")


def test_unserialisable_values_raise_and_leave_the_old_file_alone(tmp_path):
    save_settings({"a": 1}, tmp_path)
    with pytest.raises(TypeError):
        save_settings({"a": {1, 2}}, tmp_path)
    assert load_settings(tmp_path) == {"a": 1}


def test_default_folder_is_the_data_folder_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("OSU_COACH_CACHE", str(tmp_path / "data"))
    save_settings({"latest": 9})
    assert (tmp_path / "data" / "settings.json").is_file()
    assert load_settings() == {"latest": 9}


def test_empty_folder_argument_falls_back_to_the_default_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("OSU_COACH_CACHE", str(tmp_path))
    save_settings({"latest": 5}, None)
    assert load_settings("") == {"latest": 5}


@pytest.mark.parametrize("content", ["[1, 2]", '"text"', "42", "null", "true"])
def test_valid_json_that_is_not_an_object_loads_as_empty(tmp_path, content):
    (tmp_path / "settings.json").write_text(content, encoding="utf-8")
    assert load_settings(tmp_path) == {}


def test_save_leaves_no_temporary_file_behind(tmp_path):
    save_settings({"a": 1}, tmp_path)
    assert [f.name for f in tmp_path.iterdir()] == ["settings.json"]


def test_a_failed_save_keeps_the_previous_settings_file(tmp_path, monkeypatch):
    save_settings({"a": 1}, tmp_path)

    def boom(*_):
        raise OSError("disk full")

    monkeypatch.setattr("osu_coach.settings.repository.os.replace", boom)
    with pytest.raises(OSError):
        save_settings({"a": 2}, tmp_path)
    assert load_settings(tmp_path) == {"a": 1}
