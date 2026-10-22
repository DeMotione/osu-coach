import datetime as dt
import hashlib
import json
import lzma
import os
import struct
from pathlib import Path

import pytest

from osu_coach.replays import locate
from osu_coach.replays.locate import (
    DATE_SLACK_S,
    HEAD_BYTES,
    SCAN_VERSION,
    LazerStore,
    NewestReplays,
    SongsFolder,
    classify,
    file_md5,
    index_songs,
    is_osu_text,
    list_files,
    play_time,
    read_head,
    replay_header,
    scan_folder,
    scan_lazer_store,
    upgrade_index,
    walk_files,
)

STABLE = "replays/osrparse__resources__replay.osr"
MD5 = "da8aae79c8f3306b5d65ec951874a7fb"
EPOCH = dt.datetime(1970, 1, 1)
T0 = dt.datetime(2024, 5, 10, 12, 0)


# ------------------------------------------------------------------ builders
def _s(text: str) -> bytes:
    if not text:
        return b"\x00"
    raw = text.encode()
    n, out = len(raw), bytearray()
    while True:  # ULEB128 length
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            break
    return b"\x0b" + bytes(out) + raw


def osr(
    player="alice",
    when=T0,
    md5=MD5,
    version=20210101,
    mods=0,
    score=1000,
    n300=100,
    n100=0,
    n50=0,
    nmiss=0,
    life="",
    lazer_info=None,
) -> bytes:
    """A replay file with a header and no frames (that is all the scans read)."""
    ticks = int((when - dt.datetime(1, 1, 1)).total_seconds()) * 10_000_000
    out = struct.pack("<Bi", 0, version) + _s(md5) + _s(player) + _s("r" * 32)
    out += struct.pack("<6H", n300, n100, n50, 0, 0, nmiss)
    out += struct.pack("<iHBi", score, 50, 0, mods) + _s(life)
    out += struct.pack("<qi", ticks, 0)
    if lazer_info is not None:
        blob = lzma.compress(json.dumps(lazer_info).encode(), format=lzma.FORMAT_ALONE)
        out += struct.pack("<qi", 0, len(blob)) + blob
    return out


def osu_text(extra: str = "") -> bytes:
    return f"osu file format v14\n\n[General]\nAudioFilename: a.mp3\n{extra}".encode()


def put(path: Path, data: bytes, mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def epoch(when: dt.datetime) -> float:
    return when.replace(tzinfo=dt.UTC).timestamp()


def md5_of(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def store_name(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()  # lazer's content-addressed file names are 64 characters


def put_store(files_dir: Path, data: bytes, mtime: float | None = None) -> Path:
    name = store_name(data)
    return put(files_dir / name[0] / name[:2] / name, data, mtime)


# ------------------------------------------------------------------ upgrade_index
def test_upgrade_index_current_version_is_untouched():
    index = {"v": SCAN_VERSION, "osr": {"a": 1}, "lazer": {"x": {"k": "osr"}}}
    before = json.dumps(index)
    upgrade_index(index)
    assert json.dumps(index) == before


def test_upgrade_index_forgets_old_replay_headers_but_keeps_maps():
    index = {
        "v": 1,
        "osr": {"stable.osr": [1, 2, {}]},
        "files": {"a.osu": [1, 2, "md5"]},
        "lazer": {
            "h1": {"k": "osr", "h": {}},
            "h2": {"k": "osu", "md5": "m"},
            "h3": {"k": "x"},
            "h4": "not a dict",
        },
    }
    upgrade_index(index)
    assert index["v"] == SCAN_VERSION
    assert "osr" not in index
    assert set(index["lazer"]) == {"h2", "h3", "h4"}
    assert index["files"] == {"a.osu": [1, 2, "md5"]}


def test_upgrade_index_handles_an_empty_or_odd_index():
    empty: dict = {}
    upgrade_index(empty)
    assert empty == {"v": SCAN_VERSION}
    odd = {"lazer": ["not", "a", "dict"], "osr": {}}
    upgrade_index(odd)
    assert odd == {"lazer": ["not", "a", "dict"], "v": SCAN_VERSION}


def test_upgrade_index_is_idempotent():
    index = {"osr": {"a": 1}, "lazer": {"h": {"k": "osr"}}}
    upgrade_index(index)
    index["osr"] = {"new": 1}
    upgrade_index(index)
    assert index["osr"] == {"new": 1}  # already at the current version: the second call keeps new entries


# ------------------------------------------------------------------ small readers
def test_read_head_limits_the_bytes(tmp_path):
    p = put(tmp_path / "f.bin", bytes(range(256)) * 400)
    assert read_head(p) == p.read_bytes()[:HEAD_BYTES]
    assert read_head(p, 4) == b"\x00\x01\x02\x03"
    assert read_head(put(tmp_path / "empty", b"")) == b""


def test_read_head_missing_file_raises(tmp_path):
    with pytest.raises(OSError):
        read_head(tmp_path / "nope")


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (b"osu file format v14", True),
        (b"\xef\xbb\xbfosu file format v14", True),  # BOM
        (b" \t\r\n\xef\xbb\xbf osu file format v3", True),
        (b"osu file", False),
        (b"[General]\nosu file format v14", False),
        (b"", False),
        (b"\x00\x01\x02", False),
    ],
)
def test_is_osu_text(head, expected):
    assert is_osu_text(head) is expected


def test_file_md5_matches_hashlib_for_small_and_multi_chunk_files(tmp_path):
    for n in (0, 1, (1 << 20) - 1, 1 << 20, (1 << 20) + 5):
        data = (b"osu!" * (n // 4 + 1))[:n]
        assert file_md5(put(tmp_path / f"f{n}", data)) == md5_of(data)


def test_file_md5_missing_file_raises(tmp_path):
    with pytest.raises(OSError):
        file_md5(tmp_path / "nope")


def test_play_time_reads_header_timestamps_as_utc():
    assert play_time({"timestamp": "2024-05-10T12:00:00"}) == epoch(T0)
    assert play_time({"timestamp": "2024-05-10T12:00:00.500000"}) == epoch(T0) + 0.5
    assert play_time({"timestamp": EPOCH.isoformat()}) == 0.0


@pytest.mark.parametrize("h", [{}, {"timestamp": None}, {"timestamp": ""}, {"timestamp": "junk"}, {"timestamp": 5}])
def test_play_time_is_zero_for_missing_or_malformed_timestamps(h):
    assert play_time(h) == 0.0


# ------------------------------------------------------------------ walk_files / list_files
def test_walk_files_finds_suffixes_case_insensitively_in_subfolders(tmp_path):
    a = put(tmp_path / "a.osu", b"")
    b = put(tmp_path / "set" / "deep" / "B.OSU", b"")
    put(tmp_path / "set" / "c.osr", b"")
    put(tmp_path / "set" / "audio.mp3", b"")
    assert set(walk_files(tmp_path, (".osu",))) == {a, b}
    assert {p.name for p in walk_files(tmp_path, (".osu", ".osr"))} == {"a.osu", "B.OSU", "c.osr"}


def test_walk_files_of_a_missing_folder_or_a_file_is_empty(tmp_path):
    assert list(walk_files(tmp_path / "nope", (".osu",))) == []
    assert list(walk_files(put(tmp_path / "f.osu", b""), (".osu",))) == []


def test_list_files_returns_paths_with_modification_times(tmp_path):
    p = put(tmp_path / "x" / "a.osu", b"1", mtime=1_700_000_000)
    q = put(tmp_path / "b.txt", b"2", mtime=1_600_000_000)
    assert sorted(list_files(tmp_path)) == sorted([(str(p), 1_700_000_000.0), (str(q), 1_600_000_000.0)])


def test_list_files_applies_the_name_filter_to_files_only(tmp_path):
    keep = put(tmp_path / "keep.osr", b"")
    put(tmp_path / "skip.txt", b"")
    put(tmp_path / "nested.osr" / "inner.txt", b"")  # a folder named like a match is searched, not listed
    inner_keep = put(tmp_path / "nested.osr" / "inner.osr", b"")
    out = {p for p, _ in list_files(tmp_path, lambda n: n.endswith(".osr"))}
    assert out == {str(keep), str(inner_keep)}


def test_list_files_accepts_path_or_string_and_survives_missing_folders(tmp_path):
    put(tmp_path / "a", b"")
    assert len(list_files(tmp_path)) == len(list_files(str(tmp_path))) == 1
    assert list_files(tmp_path / "nope") == []
    assert list_files(tmp_path / "a") == []  # a file is not a folder


def test_list_files_does_not_follow_folder_symlinks(tmp_path):
    real = tmp_path / "real"
    put(real / "a.osr", b"")
    link = tmp_path / "scan" / "link"
    link.parent.mkdir()
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not available")

    def only_osr(name):
        return name.endswith(".osr")

    assert list_files(tmp_path / "scan", only_osr) == []  # the link's target is not searched: no loops
    assert len(list_files(tmp_path, only_osr)) == 1


def test_list_files_skips_entries_that_cannot_be_statted(tmp_path):
    ok = put(tmp_path / "ok.osr", b"")
    dangling = tmp_path / "dangling.osr"
    try:
        dangling.symlink_to(tmp_path / "gone")
    except OSError:
        pytest.skip("symlinks not available")
    # is_dir is False for the dangling link, stat() then fails: the file is skipped, the scan goes on
    assert [p for p, _ in list_files(tmp_path)] == [str(ok)]


# ------------------------------------------------------------------ replay_header
def test_replay_header_of_a_sample_replay(res):
    h = replay_header(res(STABLE))
    assert h["beatmap_md5"] == MD5
    assert h["player"] == "Cookiezi"
    assert h["path"] == str(res(STABLE))
    assert "lazer_mods" not in h


def test_replay_header_reads_a_built_replay(tmp_path):
    p = put(tmp_path / "r.osr", osr(player="bob", score=4321, n300=90, n100=10, nmiss=2, mods=64))
    h = replay_header(p)
    assert (h["player"], h["score"], h["mods"], h["mod_string"]) == ("bob", 4321, 64, "DT")
    assert h["timestamp"] == T0.isoformat()
    assert h["accuracy"] == pytest.approx((300 * 90 + 100 * 10) / (300 * 102))
    assert h["is_lazer"] is False


def test_replay_header_accepts_bytes_already_read(tmp_path):
    p = tmp_path / "does-not-exist.osr"  # the file is not touched when the head is given
    h = replay_header(p, osr(player="carol"))
    assert h["player"] == "carol" and h["path"] == str(p)


def test_replay_header_missing_or_foreign_files(tmp_path):
    assert replay_header(tmp_path / "nope.osr") is None
    assert replay_header(put(tmp_path / "t.osr", b"just some text, not a replay at all..........")) is None
    assert replay_header(put(tmp_path / "e.osr", b"")) is None


def test_replay_header_truncated_replay_is_none(tmp_path):
    data = osr()
    assert replay_header(put(tmp_path / "t.osr", data[:60])) is None  # inside the header strings
    assert replay_header(put(tmp_path / "t2.osr", data[: len(data) - 20])) is None  # inside the timestamp


def test_replay_header_reads_whole_file_for_a_very_long_life_bar(tmp_path):
    life = "0|1,100|0.5," * (HEAD_BYTES // 8)  # pushes the timestamp past the first 64 KiB
    data = osr(player="dave", life=life)
    assert len(data) > HEAD_BYTES
    h = replay_header(put(tmp_path / "long.osr", data))
    assert h is not None and h["player"] == "dave" and h["timestamp"] == T0.isoformat()


def test_replay_header_long_file_that_is_not_a_replay_stays_none(tmp_path):
    assert replay_header(put(tmp_path / "big.bin", b"x" * (HEAD_BYTES * 2))) is None


def test_replay_header_lazer_replays_carry_their_mod_acronyms(tmp_path):
    info = {"mods": [{"acronym": "dt", "settings": {"speed_change": 1.3}}, {"acronym": "HD"}, {"settings": {}}]}
    p = put(tmp_path / "lz.osr", osr(version=30000019, lazer_info=info))
    h = replay_header(p)
    assert h["is_lazer"] is True
    assert h["lazer_mods"] == ["DT", "HD"]


def test_replay_header_lazer_replay_without_score_info_has_no_mods(tmp_path):
    h = replay_header(put(tmp_path / "lz.osr", osr(version=30000001)))
    assert h["lazer_mods"] == []
    assert replay_header(put(tmp_path / "old.osr", osr(version=30000000)))["is_lazer"] is True
    assert "lazer_mods" not in replay_header(put(tmp_path / "old2.osr", osr(version=30000000)))


def test_replay_header_lazer_replay_with_garbage_score_info(tmp_path):
    data = osr(version=30000019) + struct.pack("<qi", 0, 12) + b"not lzma data"
    assert replay_header(put(tmp_path / "lz.osr", data))["lazer_mods"] == []


# ------------------------------------------------------------------ NewestReplays
def header(player="alice", when=T0, md5=MD5, score=1000) -> dict:
    return {"player": player, "timestamp": when.isoformat(), "beatmap_md5": md5, "score": score}


def hours(h: float) -> dt.datetime:
    return T0 + dt.timedelta(hours=h)


def test_newest_replays_not_done_before_enough_replays():
    picker = NewestReplays(3)
    assert not picker.done(0.0)  # nothing read yet
    picker.add(header(when=hours(0)))
    picker.add(header(when=hours(1)))
    assert not picker.done(0.0)  # two of three


def test_newest_replays_done_once_the_latest_plays_are_newer_than_the_unread_files():
    picker = NewestReplays(2)
    for h in range(3):
        picker.add(header(when=hours(h), score=h))
    # the 2nd newest play is hour 1: files older than that (plus the slack) cannot hold a newer play
    assert picker.done(epoch(hours(1)) - DATE_SLACK_S - 1)
    assert not picker.done(epoch(hours(1)) - DATE_SLACK_S)  # boundary: strictly newer is required
    assert not picker.done(epoch(hours(1)))
    assert not picker.done(epoch(hours(5)))


def test_newest_replays_keeps_only_the_newest_plays():
    picker = NewestReplays(2)
    for h, score in ((5, 1), (1, 2), (9, 3), (3, 4)):
        picker.add(header(when=hours(h), score=score))
    assert sorted(picker.newest["alice"]) == [epoch(hours(5)), epoch(hours(9))]
    assert sorted(picker.newest["*"]) == [epoch(hours(5)), epoch(hours(9))]


def test_newest_replays_ignores_duplicates():
    picker = NewestReplays(2)
    for _ in range(3):  # the same replay seen under several paths (lazer store + export)
        picker.add(header())
    assert picker.counts["alice"] == 1
    assert len(picker.newest["alice"]) == 1
    picker.add(header(score=1001))  # a different score is a different play
    assert picker.counts["alice"] == 2


def test_newest_replays_accept_filter_decides_what_counts():
    picker = NewestReplays(1, accept=lambda h: h["player"] != "bot")
    picker.add(header(player="bot", when=hours(100)))
    assert picker.counts == {} and picker.newest == {} and picker.target() is None
    picker.add(header(player="alice"))
    assert picker.target() == "alice"
    picker.add(header(player="bot", when=hours(100)))  # rejected plays are not remembered either
    assert picker.seen == {(MD5, T0.isoformat(), 1000, "alice")}


def test_newest_replays_target_is_the_most_frequent_player_by_default():
    picker = NewestReplays(5)
    assert picker.target() is None
    for i, who in enumerate(["me", "other", "me", "me", "other"]):
        picker.add(header(player=who, score=i))
    assert picker.target() == "me"


def test_newest_replays_explicit_player_wins_and_everybody_works():
    picker = NewestReplays(1, player="other")
    picker.add(header(player="me", when=hours(50), score=1))
    picker.add(header(player="me", when=hours(51), score=2))
    assert picker.target() == "other"
    assert not picker.done(0.0)  # no replay of "other" yet: keep reading
    picker.add(header(player="other", when=hours(100), score=3))
    assert picker.done(epoch(hours(0)))

    everybody = NewestReplays(2, player="*")
    everybody.add(header(player="a", when=hours(100), score=1))
    everybody.add(header(player="b", when=hours(101), score=2))
    assert everybody.done(epoch(hours(0)))


def test_newest_replays_unparsable_timestamps_count_as_the_oldest_plays():
    picker = NewestReplays(1)
    picker.add({"player": "alice", "timestamp": "junk"})
    assert picker.newest["alice"] == [0.0]
    assert not picker.done(0.0)  # play time 0 is never newer than a file
    picker.add(header())
    assert picker.newest["alice"] == [epoch(T0)]


def test_newest_replays_headers_without_a_player():
    picker = NewestReplays(1)
    picker.add({"timestamp": T0.isoformat()})
    assert picker.target() == ""
    assert not picker.done(epoch(T0))  # an unnamed player is still a player
    assert picker.done(epoch(T0) - DATE_SLACK_S - 1)


def test_newest_replays_latest_is_coerced_to_int():
    picker = NewestReplays("2")
    assert picker.latest == 2


# ------------------------------------------------------------------ scan_folder
def test_scan_folder_reads_replays_and_beatmaps_recursively(tmp_path):
    r1 = put(tmp_path / "Data" / "r" / "a.osr", osr(player="alice"))
    r2 = put(tmp_path / "Replays" / "b.osr", osr(player="bob"))
    m = put(tmp_path / "Songs" / "set" / "map.osu", osu_text())
    replays, maps = scan_folder(tmp_path, {})
    assert {h["path"] for h in replays} == {str(r1), str(r2)}
    assert {h["player"] for h in replays} == {"alice", "bob"}
    assert maps == {md5_of(osu_text()): str(m)}


def test_scan_folder_empty_or_missing_folder(tmp_path):
    assert scan_folder(tmp_path, {}) == ([], {})
    assert scan_folder(tmp_path / "nope", {}) == ([], {})


def test_scan_folder_skips_unparsable_replays_and_other_files(tmp_path):
    put(tmp_path / "bad.osr", b"not a replay, only some bytes long enough to be looked at")
    put(tmp_path / "empty.osr", b"")
    put(tmp_path / "notes.txt", b"x")
    good = put(tmp_path / "UPPER.OSR", osr())
    replays, maps = scan_folder(tmp_path, {})
    assert [h["path"] for h in replays] == [str(good)]
    assert maps == {}


def test_scan_folder_lists_replays_newest_file_first(tmp_path):
    old = put(tmp_path / "old.osr", osr(score=1), mtime=1_000_000_000)
    new = put(tmp_path / "new.osr", osr(score=2), mtime=1_700_000_000)
    mid = put(tmp_path / "mid.osr", osr(score=3), mtime=1_500_000_000)
    replays, _ = scan_folder(tmp_path, {})
    assert [h["path"] for h in replays] == [str(new), str(mid), str(old)]


def test_scan_folder_same_beatmap_twice_is_listed_once(tmp_path):
    a = put(tmp_path / "a" / "x.osu", osu_text())
    b = put(tmp_path / "b" / "y.osu", osu_text())
    _, maps = scan_folder(tmp_path, {})
    assert list(maps) == [md5_of(osu_text())]
    assert maps[md5_of(osu_text())] in (str(a), str(b))


def test_scan_folder_fills_and_reuses_the_index(tmp_path, monkeypatch):
    put(tmp_path / "a.osr", osr())
    put(tmp_path / "m.osu", osu_text())
    index: dict = {}
    first = scan_folder(tmp_path, index)
    assert len(index["osr"]) == 1 and len(index["files"]) == 1
    assert json.loads(json.dumps(index)) == index  # the index is saved as JSON between runs

    def boom(*args, **kwargs):
        raise AssertionError("an unchanged file must not be read again")

    monkeypatch.setattr(locate, "replay_header", boom)
    monkeypatch.setattr(locate, "file_md5", boom)
    assert scan_folder(tmp_path, index) == first


def test_scan_folder_cached_headers_do_not_store_the_path(tmp_path):
    p = put(tmp_path / "a.osr", osr())
    index: dict = {}
    scan_folder(tmp_path, index)
    cached = index["osr"][str(p)]
    assert "path" not in cached[2]
    assert scan_folder(tmp_path, index)[0][0]["path"] == str(p)  # but results always carry it


def test_scan_folder_changed_files_are_read_again(tmp_path):
    r = put(tmp_path / "a.osr", osr(player="alice"), mtime=1_600_000_000)
    m = put(tmp_path / "m.osu", osu_text("v1"), mtime=1_600_000_000)
    index: dict = {}
    scan_folder(tmp_path, index)
    put(r, osr(player="alice2"), mtime=1_600_000_000)  # same time, different size
    put(m, osu_text("v2"), mtime=1_600_000_500)  # different time
    replays, maps = scan_folder(tmp_path, index)
    assert replays[0]["player"] == "alice2"
    assert list(maps) == [md5_of(osu_text("v2"))]


def test_scan_folder_remembers_files_that_are_not_replays(tmp_path, monkeypatch):
    put(tmp_path / "bad.osr", b"garbage garbage garbage garbage garbage garbage")
    index: dict = {}
    scan_folder(tmp_path, index)
    (entry,) = index["osr"].values()
    assert entry[2] is None
    monkeypatch.setattr(locate, "replay_header", lambda *a: pytest.fail("read again"))
    assert scan_folder(tmp_path, index)[0] == []


def test_scan_folder_latest_stops_reading_old_files(tmp_path):
    new_play = hours(24 * 400)  # played long after the older files were written
    put(tmp_path / "new.osr", osr(when=new_play, score=2), mtime=epoch(new_play))
    old = put(tmp_path / "old.osr", osr(when=T0, score=1), mtime=epoch(T0))
    put(tmp_path / "map.osu", osu_text(), mtime=epoch(T0))
    index: dict = {}
    replays, maps = scan_folder(tmp_path, index, latest=1)
    assert [h["score"] for h in replays] == [2]
    assert str(old) not in index["osr"]  # never opened
    assert list(maps) == [md5_of(osu_text())]  # beatmaps are always indexed


def test_scan_folder_latest_reads_on_while_the_newest_plays_are_uncertain(tmp_path):
    # both files were written today, but the plays are only an hour apart: neither can be ruled out
    put(tmp_path / "a.osr", osr(when=hours(1), score=1), mtime=epoch(hours(2)))
    put(tmp_path / "b.osr", osr(when=hours(0), score=2), mtime=epoch(hours(1)))
    replays, _ = scan_folder(tmp_path, {}, latest=1)
    assert len(replays) == 2


def test_scan_folder_latest_larger_than_the_number_of_replays_reads_everything(tmp_path):
    for i in range(3):
        put(tmp_path / f"{i}.osr", osr(score=i), mtime=1_600_000_000 + i)
    assert len(scan_folder(tmp_path, {}, latest=50)[0]) == 3


@pytest.mark.parametrize("latest", [None, 0])
def test_scan_folder_without_a_positive_latest_reads_everything(tmp_path, latest):
    new_play = hours(24 * 400)
    put(tmp_path / "new.osr", osr(when=new_play, score=2), mtime=epoch(new_play))
    put(tmp_path / "old.osr", osr(when=T0, score=1), mtime=epoch(T0))
    assert len(scan_folder(tmp_path, {}, latest=latest)[0]) == 2


def test_scan_folder_latest_for_a_given_player_and_accept_filter(tmp_path):
    late = hours(24 * 400)
    put(tmp_path / "bob.osr", osr(player="bob", when=late, score=3), mtime=epoch(late))
    put(tmp_path / "alice.osr", osr(player="alice", when=hours(24 * 300), score=2), mtime=epoch(hours(24 * 300)))
    put(tmp_path / "old.osr", osr(player="alice", when=T0, score=1), mtime=epoch(T0))
    replays, _ = scan_folder(tmp_path, {}, latest=1, player="alice")
    # bob's newer replay is read, but the scan only stops once alice's newest play is certain
    assert [h["score"] for h in replays] == [3, 2]

    replays, _ = scan_folder(tmp_path, {}, latest=1, accept=lambda h: h["player"] == "alice")
    assert [h["score"] for h in replays] == [3, 2]  # accept only decides what counts, not what is returned


# ------------------------------------------------------------------ classify
def test_classify_beatmap_text_hashes_the_whole_file(tmp_path):
    data = osu_text("x" * 5000)
    assert classify(put(tmp_path / "m", data)) == {"k": "osu", "md5": md5_of(data)}
    short = b"osu file format v14"  # shorter than the 64 byte probe
    assert classify(put(tmp_path / "s", short)) == {"k": "osu", "md5": md5_of(short)}


def test_classify_beatmap_text_with_bom_and_leading_whitespace(tmp_path):
    data = b"\xef\xbb\xbf\r\nosu file format v14\r\n[General]\r\n"
    assert classify(put(tmp_path / "m", data)) == {"k": "osu", "md5": md5_of(data)}


def test_classify_big_beatmap_hashes_every_chunk(tmp_path):
    data = osu_text() + b"y" * ((1 << 20) + 123)
    assert classify(put(tmp_path / "m", data))["md5"] == md5_of(data)


def test_classify_replay_returns_its_header_without_the_path(tmp_path):
    info = classify(put(tmp_path / "r", osr(player="erin")))
    assert info["k"] == "osr"
    assert info["h"]["player"] == "erin" and "path" not in info["h"]
    assert json.loads(json.dumps(info)) == info


def test_classify_lazer_replay_keeps_its_mods(tmp_path):
    p = put(tmp_path / "r", osr(version=30000019, lazer_info={"mods": [{"acronym": "HR"}]}))
    assert classify(p)["h"]["lazer_mods"] == ["HR"]


def test_classify_long_life_bar_replay(tmp_path):
    p = put(tmp_path / "r", osr(player="fay", life="0|1," * HEAD_BYTES))
    assert classify(p)["h"]["player"] == "fay"


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\xff\xd8\xff\xe0" + b"\x00" * 100,  # jpeg
        b"ID3\x04" + b"\x00" * 100,  # mp3
        b"\x04" + b"\x00" * 100,  # mode out of range
        b"\x00" + b"\x00" * 4 + b"\x05" + b"\x00" * 60,  # right mode, no md5 string flag
    ],
)
def test_classify_everything_else_is_x(tmp_path, data):
    assert classify(put(tmp_path / "f", data)) == {"k": "x"}


def test_classify_replay_lookalike_with_a_broken_header_is_x(tmp_path):
    lookalike = b"\x00" + struct.pack("<i", 20210101) + b"\x0b" + b" " * 80
    assert classify(put(tmp_path / "f", lookalike)) == {"k": "x"}


def test_classify_unreadable_file_is_none(tmp_path):
    assert classify(tmp_path / "nope") is None
    assert classify(tmp_path) is None  # a folder


# ------------------------------------------------------------------ LazerStore
def test_lazer_store_scans_replays_and_beatmaps(tmp_path):
    files = tmp_path / "files"
    r = put_store(files, osr(player="alice"))
    m = put_store(files, osu_text())
    put_store(files, b"\x89PNG" + b"\x00" * 100)
    store = LazerStore(files, {})
    replays, maps = store.scan()
    assert [(h["player"], h["path"]) for h in replays] == [("alice", str(r))]
    assert maps == {md5_of(osu_text()): str(m)}
    assert store.exhausted


def test_lazer_store_only_looks_at_64_character_names(tmp_path):
    files = tmp_path / "files"
    put(files / "a" / "ab" / "short-name", osr())
    put(files / "a" / "ab" / ("x" * 65), osu_text())
    put(files / "a" / "ab" / ("y" * 63), osu_text())
    assert LazerStore(files, {}).scan() == ([], {})


def test_lazer_store_missing_or_empty_folder(tmp_path):
    assert LazerStore(tmp_path / "nope", {}).scan() == ([], {})
    (tmp_path / "files").mkdir()
    store = LazerStore(tmp_path / "files", {})
    assert store.scan() == ([], {})
    assert store.exhausted


def test_lazer_store_classifies_each_file_only_once(tmp_path, monkeypatch):
    files = tmp_path / "files"
    put_store(files, osr())
    put_store(files, osu_text())
    index: dict = {}
    first = LazerStore(files, index).scan()
    assert len(index["lazer"]) == 2
    monkeypatch.setattr(locate, "classify", lambda p: pytest.fail("classified again"))
    assert LazerStore(files, index).scan() == first


def test_lazer_store_cache_is_keyed_by_file_name(tmp_path):
    files = tmp_path / "files"
    r = put_store(files, osr())
    index: dict = {}
    LazerStore(files, index).scan()
    assert list(index["lazer"]) == [r.name]
    assert index["lazer"][r.name]["k"] == "osr"


def test_lazer_store_unreadable_files_are_skipped_and_not_cached(tmp_path):
    files = tmp_path / "files"
    put_store(files, osu_text())
    (files / "a" / ("d" * 64)).mkdir(parents=True)  # a folder with a store-like name: nothing to read
    index: dict = {}
    replays, maps = LazerStore(files, index).scan()
    assert replays == [] and len(maps) == 1
    assert ("d" * 64) not in index["lazer"]


def test_lazer_store_same_beatmap_under_two_names_is_listed_once(tmp_path):
    files = tmp_path / "files"
    a = put(files / "a" / ("1" * 64), osu_text())
    b = put(files / "b" / ("2" * 64), osu_text())
    _, maps = LazerStore(files, {}).scan()
    assert list(maps) == [md5_of(osu_text())] and maps[md5_of(osu_text())] in (str(a), str(b))


def test_lazer_store_progress_is_reported_every_2000_files(tmp_path):
    files = tmp_path / "files"
    for i in range(2001):
        put(files / "a" / f"{i:064d}", b"x")
    messages: list[str] = []
    LazerStore(files, {}).scan(progress=messages.append)
    assert messages == ["lazer files scanned: 2000"]


def test_lazer_store_limited_scan_leaves_old_files_unread_and_find_reads_them(tmp_path):
    files = tmp_path / "files"
    new_play = hours(24 * 400)
    new = put_store(files, osr(when=new_play, score=2), mtime=epoch(new_play))
    put_store(files, osr(when=T0, score=1), mtime=epoch(T0))
    old_map = put_store(files, osu_text("old"), mtime=epoch(T0) - 10)
    other_map = put_store(files, osu_text("other"), mtime=epoch(T0) - 20)

    store = LazerStore(files, {})
    replays, maps = store.scan(latest=1)
    assert [h["path"] for h in replays] == [str(new)]
    assert maps == {}
    assert not store.exhausted and len(store.unread) == 3

    found = store.find([md5_of(osu_text("old"))])
    assert found[md5_of(osu_text("old"))] == str(old_map)
    assert md5_of(osu_text("other")) not in found  # newest first: it stopped before reaching the older map
    assert len(store.unread) == 1 and store.unread[0][0] == str(other_map)

    found = store.find([md5_of(osu_text("other")), md5_of(osu_text("never"))])
    assert list(found) == [md5_of(osu_text("other"))]
    assert store.exhausted  # looked at everything, one beatmap does not exist


def test_lazer_store_find_returns_other_beatmaps_seen_on_the_way(tmp_path):
    files = tmp_path / "files"
    put_store(files, osr(when=hours(24 * 400)), mtime=epoch(hours(24 * 400)))
    put_store(files, osu_text("a"), mtime=epoch(T0))
    put_store(files, osu_text("b"), mtime=epoch(T0) - 10)
    store = LazerStore(files, {})
    store.scan(latest=1)
    found = store.find([md5_of(osu_text("b"))])
    assert set(found) == {md5_of(osu_text("a")), md5_of(osu_text("b"))}


def test_lazer_store_find_without_wanted_beatmaps_reads_nothing(tmp_path):
    files = tmp_path / "files"
    put_store(files, osr(when=hours(24 * 400)), mtime=epoch(hours(24 * 400)))
    put_store(files, osu_text(), mtime=epoch(T0))
    store = LazerStore(files, {})
    store.scan(latest=1)
    assert store.find([]) == {}
    assert len(store.unread) == 1


def test_lazer_store_find_before_any_scan_has_nothing_to_read(tmp_path):
    store = LazerStore(tmp_path, {})
    assert store.exhausted
    assert store.find(["abc"]) == {}


def test_lazer_store_scan_resets_the_unread_list(tmp_path):
    files = tmp_path / "files"
    put_store(files, osr(when=hours(24 * 400)), mtime=epoch(hours(24 * 400)))
    put_store(files, osu_text(), mtime=epoch(T0))
    store = LazerStore(files, {})
    store.scan(latest=1)
    assert not store.exhausted
    replays, maps = store.scan()  # a full scan afterwards reads everything
    assert store.exhausted and len(replays) == 1 and len(maps) == 1


def test_lazer_store_latest_keeps_going_when_plays_are_not_certain(tmp_path):
    files = tmp_path / "files"
    put_store(files, osr(when=hours(1), score=1), mtime=epoch(hours(2)))
    put_store(files, osr(when=hours(0), score=2), mtime=epoch(hours(1)))
    store = LazerStore(files, {})
    replays, _ = store.scan(latest=1)
    assert len(replays) == 2 and store.exhausted


def test_scan_lazer_store_scans_everything(tmp_path):
    files = tmp_path / "files"
    put_store(files, osr())
    put_store(files, osu_text())
    replays, maps = scan_lazer_store(files, {})
    assert len(replays) == 1 and len(maps) == 1


# ------------------------------------------------------------------ SongsFolder
def test_songs_folder_scan_indexes_every_beatmap(tmp_path):
    a = put(tmp_path / "1 artist - song" / "a.osu", osu_text("a"))
    b = put(tmp_path / "2 other" / "deep" / "B.OSU", osu_text("b"))
    put(tmp_path / "1 artist - song" / "audio.mp3", b"\x00")
    songs = SongsFolder(tmp_path, {})
    assert songs.scan() == {md5_of(osu_text("a")): str(a), md5_of(osu_text("b")): str(b)}
    assert songs.exhausted


def test_songs_folder_missing_or_empty(tmp_path):
    assert SongsFolder(tmp_path / "nope", {}).scan() == {}
    assert SongsFolder(tmp_path, {}).scan() == {}
    assert index_songs(tmp_path / "nope", {}) == {}


def test_songs_folder_accepts_string_paths(tmp_path):
    p = put(tmp_path / "a.osu", osu_text())
    assert SongsFolder(str(tmp_path), {}).scan() == {md5_of(osu_text()): str(p)}


def test_songs_folder_is_not_exhausted_before_a_scan_or_find(tmp_path):
    assert not SongsFolder(tmp_path, {}).exhausted


def test_songs_folder_scan_uses_and_fills_the_cache(tmp_path, monkeypatch):
    put(tmp_path / "a.osu", osu_text())
    index: dict = {}
    first = SongsFolder(tmp_path, index).scan()
    assert len(index["files"]) == 1
    monkeypatch.setattr(locate, "file_md5", lambda p: pytest.fail("hashed again"))
    assert SongsFolder(tmp_path, index).scan() == first


def test_songs_folder_shares_its_cache_with_scan_folder(tmp_path, monkeypatch):
    put(tmp_path / "a.osu", osu_text())
    index: dict = {}
    scan_folder(tmp_path, index)
    monkeypatch.setattr(locate, "file_md5", lambda p: pytest.fail("hashed again"))
    assert len(SongsFolder(tmp_path, index).scan()) == 1


def test_songs_folder_scan_progress_every_1000_files(tmp_path):
    for i in range(1001):
        put(tmp_path / f"{i}.osu", f"osu file format v14 {i}".encode())
    messages: list[str] = []
    assert len(SongsFolder(tmp_path, {}).scan(progress=messages.append)) == 1001
    assert messages == ["beatmaps indexed: 1000"]


def test_songs_folder_find_hashes_newest_files_first_and_stops_when_found(tmp_path):
    new = put(tmp_path / "new.osu", osu_text("new"), mtime=1_700_000_000)
    mid = put(tmp_path / "mid.osu", osu_text("mid"), mtime=1_600_000_000)
    old = put(tmp_path / "old.osu", osu_text("old"), mtime=1_500_000_000)
    index: dict = {}
    songs = SongsFolder(tmp_path, index)
    assert not songs.exhausted
    found = songs.find([md5_of(osu_text("mid"))])
    assert found == {md5_of(osu_text("new")): str(new), md5_of(osu_text("mid")): str(mid)}
    assert str(old) not in index["files"]  # never hashed
    assert [p for p, _ in songs.unread] == [str(old)]
    assert not songs.exhausted
    assert songs.find([md5_of(osu_text("old"))]) == {md5_of(osu_text("old")): str(old)}
    assert songs.exhausted


def test_songs_folder_find_for_an_unknown_beatmap_reads_everything(tmp_path):
    for n in ("a", "b"):
        put(tmp_path / f"{n}.osu", osu_text(n))
    songs = SongsFolder(tmp_path, {})
    found = songs.find(["0" * 32])
    assert len(found) == 2 and songs.exhausted
    assert songs.find(["0" * 32]) == {}  # nothing left to read


def test_songs_folder_find_without_wanted_beatmaps_reads_nothing(tmp_path):
    put(tmp_path / "a.osu", osu_text())
    index: dict = {}
    songs = SongsFolder(tmp_path, index)
    assert songs.find([]) == {}
    assert index["files"] == {}
    assert len(songs.unread) == 1  # listed, not hashed


def test_songs_folder_find_after_a_scan_has_nothing_left(tmp_path):
    put(tmp_path / "a.osu", osu_text())
    songs = SongsFolder(tmp_path, {})
    songs.scan()
    assert songs.find(["0" * 32]) == {}


def test_songs_folder_find_progress_every_500_files(tmp_path):
    for i in range(1000):
        put(tmp_path / f"{i}.osu", f"osu file format v14 {i}".encode())
    messages: list[str] = []
    SongsFolder(tmp_path, {}).find(["0" * 32], progress=messages.append)
    assert messages == ["looking for beatmaps in Songs: 500", "looking for beatmaps in Songs: 1000"]


def test_index_songs_is_a_songs_folder_scan(tmp_path):
    p = put(tmp_path / "a.osu", osu_text())
    assert index_songs(tmp_path, {}) == {md5_of(osu_text()): str(p)}
