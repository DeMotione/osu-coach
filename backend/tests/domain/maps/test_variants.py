"""The variant table: rows at another rate, skillset's formulas on columns, and a search that is recommend_modified's."""

import math

import numpy as np
import pandas as pd
import pytest

from osu_coach.domain.maps import skillset
from osu_coach.domain.maps.configuration import SearchOptions
from osu_coach.domain.maps.skillset import recommend_modified
from osu_coach.domain.maps.suggestions import SKILLS, skill_scores
from osu_coach.domain.maps.variants import (
    MISSING,
    PATTERN_COLUMNS,
    RATES,
    SCALES,
    VariantTable,
    composites,
    recommend_from_table,
    reference_curves,
    relevance,
    rescale,
    segment_starts,
    table_rows,
)
from osu_coach.domain.replays.configuration import Configuration
from osu_coach.infra.map_pool import load_pool


@pytest.fixture(scope="module")
def pool() -> pd.DataFrame:
    return load_pool()


def _columns(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    return {
        c: frame[c].to_numpy(dtype=float, na_value=np.nan) for c in frame if pd.api.types.is_numeric_dtype(frame[c])
    }


def test_a_statistic_follows_the_rate():
    assert rescale("stream_bpm", np.array([180.0]), 1.0, 1.5) == pytest.approx([270.0])
    assert rescale("drain_length", np.array([120.0]), 1.2, 1.5) == pytest.approx([96.0])
    assert rescale("stream_share", np.array([0.3]), 1.0, 2.0) == pytest.approx([0.3])
    # AR 9 is 600 ms of approach, 400 ms with DT: AR 10.33; AR 4 is 1320 ms, 880 ms: AR 7.13
    assert rescale("ar", np.array([9.0, 4.0]), 1.0, 1.5) == pytest.approx([10 + 1 / 3, 5 + 320 / 150])
    assert rescale("ar", np.array([10 + 1 / 3]), 1.5, 1.0) == pytest.approx([9.0])
    # OD 8: a 31.5 ms window, 21 ms with DT
    assert rescale("od", np.array([8.0]), 1.0, 1.5) == pytest.approx([(79.5 - 21) / 6])


def test_rows_are_stored_where_the_patterns_change():
    rates = np.array(RATES) / 100
    base = {"stream_bpm": 180.0, "drain_length": 100.0, "stream_share": 0.25, "ar": 9.0, "od": 8.0, "max_run": 16.0}
    rows = np.full((len(RATES), len(PATTERN_COLUMNS)), np.nan)
    for i, rate in enumerate(rates):
        for column, value in base.items():
            rows[i, PATTERN_COLUMNS.index(column)] = rescale(column, np.array(value), 1.0, rate)
    assert segment_starts(rows) == [0]
    # from 1.40 on, more notes count as a stream; at 1.80 a statistic appears that was not there
    rows[RATES.index(140) :, PATTERN_COLUMNS.index("stream_share")] = 0.4
    rows[RATES.index(180) :, PATTERN_COLUMNS.index("flow_velocity")] = rates[RATES.index(180) :] * 2
    assert segment_starts(rows) == [0, RATES.index(140), RATES.index(180)]


def test_composites_are_skillsets(pool):
    rows = pool.iloc[::37].to_dict("records")
    frame = pd.DataFrame(rows)
    for hd in (False, True):
        if hd:
            rows = [{**row, "mods": "HDDT"} for row in rows]
        mine = composites(_columns(frame), hd, SKILLS, len(rows))
        for i, row in enumerate(rows):
            theirs = skillset._features(row)
            for skill in SKILLS:
                if skill in theirs:
                    assert mine[skill][i] == pytest.approx(theirs[skill], rel=1e-12), skill
                else:
                    assert math.isnan(mine[skill][i]), skill
    assert sum(len(skillset._features(row)) for row in rows) > 6 * len(rows)


def test_relevance_is_skill_scores(pool):
    rows = pool.iloc[::41].to_dict("records")
    columns = _columns(pd.DataFrame(rows))
    for skill in SKILLS:
        mine = np.broadcast_to(relevance(columns, skill), (len(rows),))
        assert mine == pytest.approx([skill_scores(row)["s_" + skill] for row in rows], abs=1e-12), skill


def test_reference_curves_are_skillsets(pool):
    part = pool.iloc[::9]
    keys = tuple(k for k in SKILLS if k != "speed")
    mine = reference_curves(_columns(part), SKILLS)
    theirs = skillset.reference_curves(part.to_dict("records"), SKILLS)
    assert set(mine) == set(theirs) == set(keys)
    for key in keys:
        assert [v is None for v in mine[key]] == [v is None for v in theirs[key]]
        assert [v for v in mine[key] if v is not None] == pytest.approx([v for v in theirs[key] if v is not None])
        assert sum(v is not None for v in mine[key]) > 10


def _made_up_table(pool: pd.DataFrame, n: int = 90, seed: int = 5) -> tuple[VariantTable, list[dict]]:
    """A table of pool maps with made-up values: stars rising with the rate, a few configurations and one map
    without statistics, one map without a file, and maps whose patterns change at some rate."""
    rng = np.random.default_rng(seed)
    part = pool[(pool["stars"] > 2.5) & (pool["stars"] < 6.5)].sample(n=n, random_state=seed)
    records = part.to_dict("records")
    rates = np.array(RATES) / 100
    base = part["stars"].to_numpy(dtype=float)
    grow = rng.uniform(0.7, 1.0, n)
    stars = base[:, None, None, None] * rates[None, None, None, :] ** grow[:, None, None, None]
    stars = stars * np.array([1.0, 1.08])[None, :, None, None] * np.array([1.0, 1.02])[None, None, :, None]
    stars = stars + rng.normal(0, 0.03, stars.shape)
    aim = stars * rng.uniform(0.4, 0.6, (n, 1, 1, 1))
    speed = stars * rng.uniform(0.3, 0.6, (n, 1, 1, 1))
    packed = {
        k: np.rint(v * SCALES[k]).astype(np.uint16) for k, v in (("stars", stars), ("aim", aim), ("speed", speed))
    }
    packed["stars"][rng.random(stars.shape) < 0.01] = MISSING
    packed["stars"][3] = MISSING  # a map without statistics
    factor = np.rint(rng.uniform(0.9, 1.0, (n, 2, len(RATES))) * SCALES["slider_factor"]).astype(np.uint16)
    evenness = np.rint(rng.uniform(0.3, 0.9, (n, 2, len(RATES))) * SCALES["evenness"]).astype(np.uint16)
    evenness[rng.random(evenness.shape) < 0.01] = MISSING
    keys, rows = [], []
    for i, record in enumerate(records):
        for hr in (0, 1):
            row = np.array([record.get(c) for c in PATTERN_COLUMNS], dtype=np.float32)
            if hr:
                row[PATTERN_COLUMNS.index("cs")] = min(10.0, row[PATTERN_COLUMNS.index("cs")] * 1.3)
                row[PATTERN_COLUMNS.index("ar")] = min(10.0, row[PATTERN_COLUMNS.index("ar")] * 1.4)
            keys.append((i * 2 + hr) * 128)
            rows.append(row)
            if i % 4 == 0:  # other patterns from some rate on
                later = row.copy()
                at = int(rng.integers(5, 80))
                for column in ("jump_velocity", "stream_bpm", "speed_bpm", "slider_velocity", "drain_length"):
                    j = PATTERN_COLUMNS.index(column)
                    later[j] = rescale(column, np.array(row[j], dtype=np.float64), 1.0, rates[at]) * 1.1
                later[PATTERN_COLUMNS.index("stream_share")] *= 1.2
                keys.append((i * 2 + hr) * 128 + at)
                rows.append(later)
    found = np.ones(n, dtype=bool)
    found[7] = False  # a map whose file was not there
    table = VariantTable(
        md5=tuple(str(r["md5"]) for r in records),
        found=found,
        stars=packed["stars"],
        aim=packed["aim"],
        speed=packed["speed"],
        slider_factor=factor,
        evenness=evenness,
        segment_keys=np.array(keys, dtype=np.int64),
        segment_rows=np.array(rows, dtype=np.float32),
    )
    return table, records


@pytest.fixture(scope="module")
def made_up(pool):
    return _made_up_table(pool)


def test_table_rows_have_every_available_configuration(made_up):
    table, records = made_up
    options = SearchOptions(allow_hr=True, allow_hd=True, adjustable_dt=True, min_rate=1.10, max_rate=1.30)
    rows = list(table_rows(table, records, options, "lazer"))
    grid = options.configurations("", "lazer")
    assert len(grid) == 88
    stored = table.stars[
        :, [int(c.hr) for c in grid], [int(c.hd) for c in grid], [RATES.index(round(c.rate * 100)) for c in grid]
    ]
    assert len(rows) == int((stored[table.found] != MISSING).sum()) < 89 * 88
    assert [r["md5"] for r in rows] == sorted((r["md5"] for r in rows), key=[r["md5"] for r in records].index)
    by_id = {r["configuration_id"]: r for r in rows}
    assert len(by_id) == len(rows)
    record = records[1]
    md5 = record["md5"]
    plain = by_id[Configuration(md5, 0, 1.0, "lazer").key]
    assert plain["mods"] == "NM" and plain["stars_dt"] == record["stars_dt"] and plain["title"] == record["title"]
    for column in ("bpm", "drain_length", "ar", "max_run", "cs", "density_p90"):
        assert plain[column] == pytest.approx(record[column], rel=1e-6), column
    assert isinstance(plain["max_run"], int) and isinstance(plain["beatmap_id"], int)
    fast = by_id[Configuration(md5, 64 | 16 | 8, 1.25, "lazer").key]
    assert fast["mods"] == "HDHRDT" and fast["rate"] == 1.25 and "stars_dt" not in fast
    assert fast["bpm"] == pytest.approx(record["bpm"] * 1.25, rel=1e-6)
    assert fast["hit300_ms"] == pytest.approx(record["hit300_ms"] / 1.25, rel=1e-6)
    assert fast["cs"] == pytest.approx(min(10, record["cs"] * 1.3), rel=1e-6)
    assert fast["stars"] == table.stars[1, 1, 1, RATES.index(125)] / 1000
    assert fast["s_aim"] == skill_scores(fast)["s_aim"]
    # a map whose patterns change at a rate has the other row from that rate on
    changed = next(
        i for i in range(0, len(records), 4) if table.segment_keys[table.segment_keys // 256 == i][1] % 128 < 21
    )
    at = int(table.segment_keys[table.segment_keys // 256 == changed][1] % 128)
    md5 = records[changed]["md5"]
    before = by_id.get(Configuration(md5, 64, RATES[at - 1] / 100, "lazer").key)
    after = by_id.get(Configuration(md5, 64, RATES[at] / 100, "lazer").key)
    if before and after:
        assert after["stream_share"] == pytest.approx(before["stream_share"] * 1.2, rel=1e-5)


SEARCHES = [
    # skill, assessed, abilities, comfort, options, limit
    ("aim", ("aim",), {"aim": 50.0}, 4.2, SearchOptions(True, True, True, 1.10, 1.40), 100),
    ("aim", ("aim",), {"aim": 62.0}, 4.2, SearchOptions(True, True, True, 1.10, 1.40), 6),
    (
        "speed",
        ("speed", "aim", "reading"),
        {"speed": 45.0, "aim": 55.0, "reading": 40.0},
        5.0,
        SearchOptions(True, True, True, 1.10, 1.60),
        8,
    ),
    (
        "reading",
        SKILLS,
        dict.fromkeys(SKILLS, 50.0) | {"reading": 35.0, "stamina": 70.0},
        4.6,
        SearchOptions(False, True, True, 1.10, 1.50),
        5,
    ),
    (
        "sliders",
        ("sliders", "consistency"),
        {"sliders": 58.0, "consistency": 30.0},
        3.6,
        SearchOptions(True, False, False),
        4,
    ),
    (
        "stamina",
        ("stamina", "flow_aim", "accuracy"),
        {"stamina": 52.0, "flow_aim": 48.0, "accuracy": 66.0},
        5.4,
        SearchOptions(True, True, True, 1.20, 2.00),
        100,
    ),
    ("consistency", ("consistency",), {"consistency": 50.0}, 4.0, SearchOptions(True, True, False), 3),
    (
        "accuracy",
        ("accuracy", "speed"),
        {"accuracy": 44.0, "speed": 80.0},
        4.9,
        SearchOptions(False, False, True, 1.10, 2.00),
        10,
    ),
]


@pytest.mark.parametrize(("skill", "assessed", "abilities", "theta", "options", "limit"), SEARCHES)
def test_the_table_search_is_recommend_modified_on_every_row(
    made_up, pool, skill, assessed, abilities, theta, options, limit
):
    table, records = made_up
    columns = _columns(pool)
    played = frozenset(str(r["md5"]) for r in records[10:16])
    grid = options.configurations("", "lazer")
    history = {
        Configuration(str(records[20 + i]["md5"]), grid[i % len(grid)].mods, grid[i % len(grid)].rate, "lazer").key: 0.2
        + 0.2 * i
        for i in range(5)
    }
    history["not a configuration"] = 0.5
    history[Configuration(str(records[30]["md5"]), 0, 1.0, "stable").key] = 0.1  # another client's
    found = recommend_from_table(
        table, records, columns, options, "lazer", theta, abilities, skill, assessed, 0.5, 0.3, played, history, limit
    )
    rows = list(table_rows(table, records, options, "lazer"))
    references = reference_curves(columns, assessed)
    whole = recommend_modified(
        records, rows, theta, abilities, skill, assessed, 0.5, 0.3, played, history, limit, references
    )
    mine = found.recommendation
    assert mine.candidate_count == whole.candidate_count == len(rows)
    for goal in whole.goals:
        a, b = mine.goals[goal], whole.goals[goal]
        assert [m.configuration_id for m in a.maps] == [m.configuration_id for m in b.maps], goal
        assert a.excluded == b.excluded and a.eligible == b.eligible, goal
    assert mine == whole
    assert sum(len(g.maps) for g in whole.goals.values()) > 0
    assert (found.maps, found.missing_maps, found.unusable_maps) == (len(records) - 1, 1, 1)
    assert found.unavailable_configurations == (len(records) - 1) * len(grid) - len(rows)


def test_a_search_without_a_rating_looks_nothing_up(made_up, pool):
    table, records = made_up
    found = recommend_from_table(
        table, records, _columns(pool), SearchOptions(True), "lazer", 4.0, {"aim": 50.0}, "aim", ("aim", "speed"),
        0.5, 0.3, frozenset(), {},
    )  # fmt: skip
    assert (found.maps, found.missing_maps, found.unusable_maps, found.unavailable_configurations) == (0, 0, 0, 0)
    assert all(g.excluded == {"Assessed player rating unknown": 1} for g in found.recommendation.goals.values())
    with pytest.raises(ValueError, match="positive comfort"):
        recommend_from_table(
            table, records, _columns(pool), SearchOptions(True), "lazer", 0.0, {"aim": 50.0}, "aim", ("aim",),
            0.5, 0.3, frozenset(), {},
        )  # fmt: skip
