import struct

import pytest

from osu_coach.exports import collection_db as coll

H1 = "0123456789abcdef0123456789abcdef"
H2 = "fedcba9876543210fedcba9876543210"
H3 = "00000000000000000000000000000001"


def test_exact_bytes_of_a_tiny_collection():
    data = coll.dumps({"A": [H1]})
    expected = (
        struct.pack("<ii", coll.DEFAULT_VERSION, 1) + b"\x0b\x01A" + struct.pack("<i", 1) + b"\x0b\x20" + H1.encode()
    )
    assert data == expected


def test_roundtrip_keeps_order_and_drops_duplicates():
    data = coll.dumps({"osu-coach: Aim": [H1, H2, H1], "Second": [H3]}, version=20240101)
    version, cols = coll.loads(data)
    assert version == 20240101
    assert cols == [("osu-coach: Aim", [H1, H2]), ("Second", [H3])]


def test_long_and_unicode_names_use_uleb128_lengths():
    name = "練習 " * 60  # > 127 bytes -> 2-byte ULEB128 length
    _, cols = coll.loads(coll.dumps({name: [H1]}))
    assert cols[0][0] == name


def test_null_strings_are_read_as_empty():
    data = struct.pack("<ii", 20150203, 1) + b"\x00" + struct.pack("<i", 1) + b"\x00"
    assert coll.loads(data) == (20150203, [("", [""])])


def test_merge_replaces_same_name_keeps_others_and_backs_up(tmp_path):
    db = tmp_path / "collection.db"
    original = coll.dumps({"Mine": [H3], "osu-coach: Aim": [H1]}, version=20250101)
    db.write_bytes(original)
    info = coll.merge_into(db, {"osu-coach: Aim": [H2], "osu-coach: Speed": [H3]})
    version, cols = coll.read_collection_db(db)
    assert version == 20250101  # user's file version preserved
    assert cols == [("Mine", [H3]), ("osu-coach: Aim", [H2]), ("osu-coach: Speed", [H3])]
    assert info["replaced"] == ["osu-coach: Aim"] and info["added"] == ["osu-coach: Speed"]
    assert info["backup"] and open(info["backup"], "rb").read() == original


def test_merge_creates_missing_file(tmp_path):
    db = tmp_path / "collection.db"
    info = coll.merge_into(db, {"osu-coach: Aim": [H1]})
    assert info["backup"] is None
    assert coll.read_collection_db(db)[1] == [("osu-coach: Aim", [H1])]


def test_truncated_file_raises_value_error():
    with pytest.raises(ValueError):
        coll.loads(coll.dumps({"A": [H1]})[:-5])
