import hashlib

from tests.conftest import sample_paths

from osu_coach.library.repository import Library
from osu_coach.play_goals.repository import target_bytes, target_configuration


def test_target_outside_goal_pool_resolves_from_local_library(tmp_path):
    _, path = sample_paths("mot1one__lazer_nm.osr")
    library = Library(tmp_path)
    library.add_files([path])
    from osu_coach.beatmaps.parser import parse_beatmap_bytes

    raw = path.read_bytes()
    beatmap = parse_beatmap_bytes(raw)
    assert target_bytes(tmp_path, beatmap.beatmap_id, [library], False, []) == raw


def test_configuration_cache_is_separate_for_client_mods_and_checksums(tmp_path):
    _, path = sample_paths("mot1one__lazer_nm.osr")
    raw = path.read_bytes()
    nm = target_configuration(tmp_path, raw, "NM", "stable")
    hd = target_configuration(tmp_path, raw, "HD", "stable")
    lazer = target_configuration(tmp_path, raw, "NM", "lazer")
    assert nm["md5"] == hd["md5"] == lazer["md5"] == hashlib.md5(raw).hexdigest()
    assert hd["mods"] == "HD" and lazer["client"] == "lazer"
    assert target_configuration(tmp_path, raw, "NM", "stable") == nm
    assert len(list((tmp_path / "play-goals" / "configurations").glob("*.json"))) == 3
