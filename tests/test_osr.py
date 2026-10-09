import numpy as np
import osrparse
import pytest

from osu_coach.osr import parse_replay_file, mods_to_string, rate_from_mods

STABLE = "replays/osrparse__resources__replay.osr"
LAZER = "replays/osrparse__resources__lazer_standard_format.osr"


def test_reads_header_of_stable_replay(res):
    r = parse_replay_file(res(STABLE))
    assert r.mode == 0
    assert r.player == "Cookiezi"
    assert r.beatmap_md5 == "da8aae79c8f3306b5d65ec951874a7fb"
    assert (r.n300, r.n100, r.n50, r.nmiss) == (1982, 1, 0, 0)
    assert r.mods == 0
    assert r.timestamp.year >= 2007


def test_frames_match_osrparse_except_skip_frame_offset(res):
    """Same frames as osrparse, but (like lazer/stable) the deltas of the two
    dropped (256,-500) skip frames are carried into the absolute time."""
    path = res(STABLE)
    ours = parse_replay_file(path)
    ref = osrparse.Replay.from_path(path)
    ref_t = np.cumsum([e.time_delta for e in ref.replay_data])
    assert len(ours.t) == len(ref_t)
    assert np.array_equal(np.diff(ours.t), np.diff(ref_t))
    assert ours.t[0] == 0  # raw stream starts 0|256|-500, -1|256|-500, 1|552...
    assert np.allclose(ours.x, [e.x for e in ref.replay_data])
    assert np.array_equal(ours.keys, [int(e.keys) for e in ref.replay_data])
    assert np.all(np.diff(ours.t) >= 0), "frame times must never go backwards"


def test_old_lazer_export_parses_without_score_info(res):
    r = parse_replay_file(res(LAZER))
    assert r.version == 30000000 and r.is_lazer
    assert r.lazer is None  # score-info blob only exists from version 30000001
    assert r.nmiss == 37 and len(r.t) > 1000


def test_lazer_score_info_blob_is_decoded(res):
    """Build a 30000001+ replay: stable bytes + int length + LZMA(JSON)."""
    import json
    import lzma
    import struct

    raw = bytearray(res(STABLE).read_bytes())
    raw[1:5] = struct.pack("<i", 30000019)
    info = {"mods": [{"acronym": "DT", "settings": {"speed_change": 1.3}}], "statistics": {"great": 5, "miss": 1}}
    blob = lzma.compress(json.dumps(info).encode(), format=lzma.FORMAT_ALONE)
    raw += struct.pack("<i", len(blob)) + blob
    from osu_coach.osr import parse_replay

    r = parse_replay(bytes(raw))
    assert r.lazer["statistics"]["great"] == 5
    assert r.rate == pytest.approx(1.3)


@pytest.mark.parametrize("mods,rate", [(0, 1.0), (64, 1.5), (576, 1.5), (256, 0.75), (16 + 8, 1.0)])
def test_rate_from_legacy_mods(mods, rate):
    assert rate_from_mods(mods) == rate


def test_mod_string():
    assert mods_to_string(0) == "NM"
    assert mods_to_string(8 + 64) == "HDDT"
    assert mods_to_string(576) == "NC"
    assert mods_to_string(16 + 8) == "HDHR"
