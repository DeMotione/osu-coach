"""The pool's table of mod and rate configurations: its rows are the ones worked out from the map files."""

import hashlib
import json
import zipfile

import numpy as np
import pytest

from osu_coach.domain.maps.configuration import SearchOptions
from osu_coach.domain.maps.skillset import Screened
from osu_coach.features.maps import variant_table as vt
from osu_coach.features.maps.variant_repository import calculate_variants
from osu_coach.infra.beatmaps import difficulty

pytestmark = pytest.mark.skipif(not difficulty.available(), reason="rosu-pp-py not installed")

MAPS = ("0619c930348063c2a967a3af4d69cd6b", "05f7ba8a18b4d7a29a9e8f79c5b7b3e6")
# kept to 4 decimals (aim, speed and evenness 3), so the rows differ from the exact ones by a rounding
ROUNDING = 1e-3


@pytest.fixture(scope="module")
def maps(request):
    res = request.config.rootpath / "tests" / "resources" / "maps"
    files = sorted(res.glob("*.osu"))[:2]
    return [(hashlib.md5(f.read_bytes()).hexdigest(), f.read_bytes()) for f in files]


@pytest.fixture(scope="module")
def entries(maps):
    return [vt.build_map(raw) for _, raw in maps]


@pytest.fixture(scope="module")
def targets(entries):
    """Goals a little above each map's own stars: reached with a rate, with Hard Rock, or both."""
    return tuple(float(e["stars"][0, 0]) / 1e4 * 1.25 for e in entries)


def _table(tmp_path, md5s, entries):
    path = tmp_path / "variants.zip"
    vt.write_table(path, [vt.pack_chunk(md5s, entries)], len(md5s))
    return vt.load(path)


def _records(md5s):
    return [
        {
            "md5": md5,
            "title": f"map {i}",
            "artist": "A",
            "version": "V",
            "creator": "C",
            "beatmap_id": i + 1,
            "beatmapset_id": 9,
        }
        for i, md5 in enumerate(md5s)
    ]


def test_rows_are_the_ones_made_from_the_map_files(maps, entries, targets, tmp_path):
    md5s = [md5 for md5, _ in maps]
    table = _table(tmp_path, md5s, entries)
    options = SearchOptions(allow_hr=True, allow_hd=True, adjustable_dt=True, min_rate=1.2, max_rate=1.6)
    results = {
        index: (known, rows, failed, asked)
        for index, known, rows, failed, asked in table.results(_records(md5s), options, "stable", targets)
    }
    compared = 0
    for index, (md5, raw) in enumerate(maps):
        configs = options.configurations(md5)
        want, unavailable = calculate_variants(tmp_path, raw, configs, targets)
        known, got, failed, asked = results[index]
        assert known and failed == unavailable and asked == len(configs)
        exact = {r["configuration_id"]: r for r in want if isinstance(r, dict)}
        mine = {r["configuration_id"]: r for r in got if isinstance(r, dict)}
        assert set(mine) == set(exact)
        assert [(s.outside, s.no_stars) for s in got if isinstance(s, Screened)] == [
            (s.outside, s.no_stars) for s in want if isinstance(s, Screened)
        ]
        for key, row in exact.items():
            compared += 1
            for name, value in row.items():
                if name == "speed_note_count":  # not read by any ranking: not kept
                    continue
                other = mine[key][name]
                if name in ("title", "artist", "version", "creator", "beatmap_id", "beatmapset_id"):
                    assert other == _records(md5s)[index][name]  # the pool's, as with_pool_ids gives them
                elif isinstance(value, (int, float)) and not isinstance(value, bool) and value is not None:
                    assert other == pytest.approx(value, abs=ROUNDING), (name, key)
                else:
                    assert other == value, (name, key)
            assert set(mine[key]) == set(row) - {"speed_note_count"}
    assert compared > 20


def test_statistics_follow_the_rate_or_are_kept_for_every_rate(maps):
    """Where the statistics at a rate aren't the ones at rate 1 scaled, the table keeps them: checking every rate
    finds nothing more to keep than the quick rule does."""
    raw = maps[0][1]
    quick, checked = vt.build_map(raw), vt.build_map(raw, check_every_rate=True)
    assert checked["differs"].tolist() == quick["differs"].tolist()
    assert (checked["base"] == quick["base"]).all()


def test_a_part_packs_and_unpacks_to_the_same_numbers(maps, entries):
    md5s = [md5 for md5, _ in maps] + ["f" * 32]
    chunk = vt._unpack_chunk(vt.pack_chunk(md5s, [*entries, None]))
    assert chunk["md5"].tolist() == md5s and chunk["present"].tolist() == [True, True, False]
    for name in ("stars", "aim", "speed", "slider", "combo", "even", "base"):
        assert (chunk[name][:2] == np.array([e[name] for e in entries])).all(), name
    assert (chunk["stars"][2] == 0).all()


def test_maps_without_data_played_maps_and_lazer(maps, entries, targets, tmp_path):
    md5s = [md5 for md5, _ in maps]
    differs_in_lazer = {**entries[1], "same": np.array([False, True])}
    table = _table(tmp_path, [md5s[0], md5s[1], "f" * 32], [entries[0], differs_in_lazer, None])
    records = _records([*md5s, "f" * 32, "e" * 32])  # the last one isn't in the table at all
    options = SearchOptions(adjustable_dt=True)

    def run(client, played=frozenset()):
        return {
            i: (known, rows, failed)
            for i, known, rows, failed, _ in table.results(records, options, client, targets, played)
        }

    stable = run("stable")
    assert [stable[i][0] for i in range(4)] == [True, True, False, False]
    assert any(isinstance(r, dict) for r in stable[0][1])
    assert all(
        r["configuration_id"] == vt.Configuration(md5s[0], 64 if r["rate"] != 1 else 0, r["rate"], "stable").key
        for r in stable[0][1]
        if isinstance(r, dict)
    )
    # a map lazer calculates differently has no data for a lazer player
    assert [run("lazer")[i][0] for i in range(4)] == [True, False, False, False]
    # a played map is only counted: every configuration with stars, none ranked
    played = run("stable", frozenset({md5s[0]}))[0][1]
    assert [type(r) for r in played] == [Screened]
    rows = [r for r in stable[0][1] if isinstance(r, dict)]
    screened = [r for r in stable[0][1] if isinstance(r, Screened)]
    assert played[0].outside == len(rows) + sum(s.outside for s in screened)


def test_a_table_of_another_version_is_not_used(maps, entries, tmp_path):
    md5s = [md5 for md5, _ in maps]
    path = tmp_path / "variants.zip"
    vt.write_table(path, [vt.pack_chunk(md5s, entries)], 2)
    assert vt.load(path) is not None
    old = tmp_path / "old.zip"
    with zipfile.ZipFile(path) as z, zipfile.ZipFile(old, "w") as out:
        for name in z.namelist():
            data = z.read(name)
            out.writestr(name, json.dumps({**json.loads(data), "calculator": "0.0.0"}) if name == "meta.json" else data)
    assert vt.load(old) is None
    assert vt.load(tmp_path / "missing.zip") is None


def test_search_ranks_from_the_table_without_map_files(maps, entries, targets, tmp_path, monkeypatch):
    from osu_coach.features.maps import service

    md5s = [md5 for md5, _ in maps]
    monkeypatch.setenv("OSU_COACH_VARIANTS", str(_table(tmp_path, md5s, entries).path))

    def no_files(*args, **kwargs):
        raise AssertionError("the map files aren't read when the table is there")

    monkeypatch.setattr(service, "_search_map_results", no_files)
    monkeypatch.setattr(service, "verified_bytes", no_files)
    seen = {}

    def capture(base_pool, variants, *args, **kwargs):
        seen["rows"] = [v for v in variants if isinstance(v, dict)]
        raise RuntimeError("ranked")

    monkeypatch.setattr(service, "recommend_modified", capture)
    from types import SimpleNamespace

    import pandas as pd

    from osu_coach.infra.settings import UserSettings

    ws = SimpleNamespace(
        pool=lambda: pd.DataFrame(_records(md5s)).assign(stars=6.0),
        profile=lambda: None,
        settings=lambda: UserSettings(),
        library=None,
        plays=[],
        libraries=lambda: [],
        preferred_client=lambda: "stable",
        cache_dir=tmp_path,
    )
    # a rating of 50 leaves the Comfort goal at the comfort level: the first map's goal
    request = service.PlaylistSearchRequest(
        skill="aim", comfort=targets[0], ratings=json.dumps({"aim": 50}), adjustable_dt=True, allow_hr=True
    )
    with pytest.raises(RuntimeError, match="ranked"):
        service.search(ws, request, lambda *a: None)
    assert seen["rows"] and {r["md5"] for r in seen["rows"]} <= set(md5s)
    assert all(r["title"].startswith("map ") for r in seen["rows"])


def test_relevance_of_many_rows_is_the_domains(entries):
    """The table works out skill_scores for all rows at once: the same numbers as the domain's, row by row."""
    from osu_coach.domain.maps.suggestions import skill_scores

    rng = np.random.default_rng(0)
    names = (*vt.PATTERN, "aim", "speed", "slider_factor", "evenness")
    table = {name: rng.uniform(0, 1, 400) for name in names}
    table.update(
        aim=rng.uniform(0, 6, 400), speed=rng.uniform(0, 6, 400), od=rng.uniform(3, 11, 400),
        stream_notes=rng.uniform(0, 600, 400), max_run=rng.uniform(0, 64, 400), drain_length=rng.uniform(30, 400, 400),
        density_p90=rng.uniform(1, 14, 400), slider_factor=rng.uniform(0.85, 1, 400),
    )  # fmt: skip
    for name in names:  # statistics a map doesn't have
        table[name][rng.integers(0, 400, 12)] = np.nan
    table["aim"][:3] = table["speed"][:3] = 0
    many = vt._skill_scores(table)
    for i in range(400):
        one = skill_scores({name: float(table[name][i]) for name in names})
        assert {k: float(many[k][i]) for k in one} == pytest.approx(one, abs=1e-12)
