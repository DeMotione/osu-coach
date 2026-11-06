"""The uploads folder: names are made safe, and files are only ever looked up inside it."""

import pytest

from osu_coach.common.errors import ApiError
from osu_coach.infra.uploads import find_upload, known_replay, safe_upload_name, upload_target, uploads_dir


@pytest.mark.parametrize(
    ("name", "safe"),
    [
        ("play.osr", "play.osr"),
        ("../../evil.osr", "evil.osr"),
        ("..\\..\\evil.osr", "evil.osr"),
        ("C:\\Windows\\evil.osr", "evil.osr"),
        ("my<map>|v2?.osr", "my_map_v2_.osr"),
        ("..", "upload"),
        ("NUL.osr", "_NUL.osr"),
        ("com1.tar.osr", "_com1.tar.osr"),
        ("console.osr", "console.osr"),  # only the exact device names
        ("x" * 179 + ".osr", "x" * 179),  # cut to 180 characters, then no dot at the end
    ],
)
def test_upload_names_are_safe(name, safe):
    assert safe_upload_name(name) == safe


def test_an_upload_is_found_only_inside_the_uploads_folder(tmp_path):
    cache = tmp_path / "cache"
    folder = uploads_dir(cache)
    (folder / "play.osr").write_bytes(b"x")
    (folder / "folder.osr").mkdir()
    outside = tmp_path / "outside.osr"  # a real file next to the data folder
    outside.write_bytes(b"x")
    assert find_upload(cache, "play.osr") == folder / "play.osr"
    assert find_upload(cache, "missing.osr") is None
    assert find_upload(cache, "folder.osr") is None  # not a file
    assert find_upload(cache, "../outside.osr") is None  # becomes outside.osr, which isn't in the folder
    assert find_upload(cache, str(outside)) is None
    assert find_upload(cache, "../uploads/play.osr") == folder / "play.osr"  # only its name counts


def test_uploads_are_saved_inside_the_uploads_folder(tmp_path):
    folder = uploads_dir(tmp_path)
    for name in ("play.osr", "../../evil.osr", "..\\evil.osr", "NUL.osr", ".."):
        assert upload_target(tmp_path, name).parent == folder


def test_a_replay_path_must_be_the_one_the_upload_got(tmp_path):
    cache = tmp_path / "cache"
    uploaded = uploads_dir(cache) / "play.osr"
    uploaded.write_bytes(b"x")
    assert known_replay(str(uploaded), cache, [None]) == uploaded
    elsewhere = tmp_path / "play.osr"  # same name, other folder
    elsewhere.write_bytes(b"x")
    with pytest.raises(ApiError) as err:
        known_replay(str(elsewhere), cache, [None])
    assert err.value.code == "replay_not_found"
