import datetime as dt

import pytest

from osu_coach.replays import scope
from osu_coach.replays.scope import (
    best_replays,
    date_window,
    filter_refs,
    in_window,
    last_session_start,
    parse_time,
    select,
    speed_of,
)

UTC = dt.UTC
T0 = dt.datetime(2024, 5, 10, 12, 0, tzinfo=UTC)


def at(minutes: float) -> dt.datetime:
    return T0 + dt.timedelta(minutes=minutes)


def play(md5="m1", score=1000, acc=0.9, rate=None, completed=True, **extra) -> dict:
    return {
        "beatmap_md5": md5,
        "score": score,
        "accuracy": acc,
        "rate": rate,
        "completed": completed,
        **extra,
    }


# ------------------------------------------------------------------ constants
def test_choices_and_labels_agree():
    assert set(scope.DATE_CHOICES) == set(scope.DATE_LABELS)
    assert set(scope.REPLAY_SETS) == set(scope.REPLAY_SET_LABELS)
    assert scope.DATE_CHOICES[0] == "all" and scope.REPLAY_SETS[0] == "all"  # the defaults come first


# ------------------------------------------------------------------ parse_time
@pytest.mark.parametrize("v", [None, "", "not a date", "2024-13-45T00:00:00"])
def test_parse_time_rejects_missing_and_malformed(v):
    assert parse_time(v) is None


def test_parse_time_treats_naive_values_as_utc():
    assert parse_time("2024-05-10T12:00:00") == T0
    assert parse_time(dt.datetime(2024, 5, 10, 12, 0)) == T0
    assert parse_time("2024-05-10T12:00:00").tzinfo is not None


def test_parse_time_converts_offsets_to_utc():
    t = parse_time("2024-05-10T14:00:00+02:00")
    assert t == T0 and t.utcoffset() == dt.timedelta(0)
    aware = dt.datetime(2024, 5, 10, 7, 0, tzinfo=dt.timezone(dt.timedelta(hours=-5)))
    assert parse_time(aware) == T0


def test_parse_time_accepts_z_suffix_and_microseconds():
    assert parse_time("2024-05-10T12:00:00Z") == T0
    assert parse_time("2024-05-10T12:00:00.250000") == T0 + dt.timedelta(milliseconds=250)


# ------------------------------------------------------------------ last_session_start
def test_last_session_start_without_plays():
    assert last_session_start([]) is None
    assert last_session_start([None, "", "junk"]) is None


def test_last_session_start_single_play_is_its_own_session():
    assert last_session_start([at(0).isoformat()]) == at(0)


def test_last_session_start_stops_at_the_first_long_pause():
    times = [at(0), at(30), at(60), at(200), at(230)]  # 140 minute pause before the last three plays
    assert last_session_start(times) == at(200)


def test_last_session_start_input_order_does_not_matter():
    times = [at(230), at(0), at(200), at(60), at(30)]
    assert last_session_start(times) == at(200)


def test_last_session_start_chains_plays_longer_than_the_gap_in_total():
    times = [at(m) for m in range(0, 301, 50)]  # 50 minutes apart: one session of five hours
    assert last_session_start(times) == at(0)


def test_last_session_start_gap_boundary_is_inclusive():
    exactly = [at(0), at(60)]
    assert last_session_start(exactly) == at(0)  # a pause of exactly SESSION_GAP still continues the session
    just_over = [at(0), at(60) + dt.timedelta(seconds=1)]
    assert last_session_start(just_over) == just_over[1]


def test_last_session_start_custom_gap():
    times = [at(0), at(20), at(25)]
    assert last_session_start(times, gap=dt.timedelta(minutes=10)) == at(20)
    assert last_session_start(times, gap=dt.timedelta(minutes=20)) == at(0)


def test_last_session_start_skips_unparsable_times_and_mixes_types():
    times = ["junk", None, at(10).isoformat(), at(0).replace(tzinfo=None), "2024-05-10T12:20:00Z"]
    assert last_session_start(times) == at(0)


def test_last_session_start_accepts_a_generator():
    assert last_session_start(at(m) for m in (0, 10)) == at(0)


# ------------------------------------------------------------------ date_window
@pytest.mark.parametrize("choice", ["all", "", "nonsense"])
def test_date_window_open_for_all_and_unknown_choices(choice):
    assert date_window(choice, times=[at(0)], now=T0) == (None, None)


@pytest.mark.parametrize(("choice", "days"), [("7d", 7), ("30d", 30)])
def test_date_window_counts_back_from_now(choice, days):
    assert date_window(choice, now=T0) == (T0 - dt.timedelta(days=days), None)


def test_date_window_now_may_be_naive_or_a_string():
    assert date_window("7d", now=T0.replace(tzinfo=None)) == date_window("7d", now=T0)
    assert date_window("7d", now="2024-05-10T14:00:00+02:00") == date_window("7d", now=T0)


def test_date_window_defaults_to_the_current_time():
    before = dt.datetime.now(UTC)
    since, until = date_window("30d")
    after = dt.datetime.now(UTC)
    assert until is None
    assert before - dt.timedelta(days=30) <= since <= after - dt.timedelta(days=30)


def test_date_window_session_uses_the_replay_times():
    times = [at(0), at(500), at(530)]
    assert date_window("session", times=times, now=T0) == (at(500), None)
    assert date_window("session", times=[], now=T0) == (None, None)  # nothing to anchor a session on
    assert date_window("session") == (None, None)


def test_date_window_custom_range_includes_both_days():
    tz = dt.UTC
    since, until = date_window("custom", start=dt.date(2024, 5, 1), end=dt.date(2024, 5, 3), tz=tz)
    assert since == dt.datetime(2024, 5, 1, tzinfo=UTC)
    assert until == dt.datetime(2024, 5, 4, tzinfo=UTC)  # end of 3 May = start of 4 May, exclusive


def test_date_window_custom_range_is_local_calendar_days():
    tz = dt.timezone(dt.timedelta(hours=2))
    since, until = date_window("custom", start=dt.date(2024, 5, 1), end=dt.date(2024, 5, 1), tz=tz)
    assert since == dt.datetime(2024, 4, 30, 22, 0, tzinfo=UTC)
    assert until == dt.datetime(2024, 5, 1, 22, 0, tzinfo=UTC)
    assert since.utcoffset() == dt.timedelta(0)


def test_date_window_custom_range_with_one_open_end():
    tz = dt.UTC
    assert date_window("custom", start=dt.date(2024, 5, 1), tz=tz) == (dt.datetime(2024, 5, 1, tzinfo=UTC), None)
    assert date_window("custom", end=dt.date(2024, 5, 1), tz=tz) == (None, dt.datetime(2024, 5, 2, tzinfo=UTC))
    assert date_window("custom", tz=tz) == (None, None)


def test_date_window_custom_range_defaults_to_the_local_time_zone():
    since, until = date_window("custom", start=dt.date(2024, 5, 1), end=dt.date(2024, 5, 1))
    assert since.utcoffset() == dt.timedelta(0)
    assert until - since == dt.timedelta(days=1)  # holds for any fixed local offset
    assert abs(since - dt.datetime(2024, 5, 1, tzinfo=UTC)) <= dt.timedelta(hours=14)


def test_date_window_custom_range_ending_before_it_starts_matches_nothing():
    since, until = date_window("custom", start=dt.date(2024, 5, 5), end=dt.date(2024, 5, 1), tz=dt.UTC)
    refs = [{"timestamp": dt.datetime(2024, 5, d, 12).isoformat()} for d in range(1, 8)]
    assert filter_refs(refs, since, until) == []


# ------------------------------------------------------------------ in_window / filter_refs
def test_in_window_bounds_are_since_inclusive_until_exclusive():
    since, until = at(0), at(60)
    assert in_window(at(0), since, until)
    assert in_window(at(59.99), since, until)
    assert not in_window(at(60), since, until)
    assert not in_window(at(-0.01), since, until)


def test_in_window_open_ends():
    assert in_window(at(1000), at(0), None)
    assert not in_window(at(-1), at(0), None)
    assert in_window(at(-1000), None, at(0))
    assert in_window(at(0), None, None)


def test_in_window_without_a_time_only_passes_an_unbounded_window():
    assert in_window(None, None, None)
    assert in_window("junk", None, None)
    assert not in_window(None, at(0), None)
    assert not in_window("", None, at(0))


def test_in_window_reads_header_strings():
    assert in_window("2024-05-10T12:30:00", at(0), at(60))
    assert not in_window("2024-05-10T13:30:00", at(0), at(60))


def test_filter_refs_without_bounds_returns_a_copy():
    refs = [{"timestamp": "2024-05-10T12:00:00"}, {}]
    out = filter_refs(refs, None, None)
    assert out == refs and out is not refs  # even entries without a timestamp are kept


def test_filter_refs_keeps_plays_inside_the_window():
    refs = [{"id": i, "timestamp": at(m).replace(tzinfo=None).isoformat()} for i, m in enumerate((-5, 0, 30, 60, 90))]
    assert [r["id"] for r in filter_refs(refs, at(0), at(60))] == [1, 2]
    assert [r["id"] for r in filter_refs(refs, at(30), None)] == [2, 3, 4]
    assert [r["id"] for r in filter_refs(refs, None, at(30))] == [0, 1]


def test_filter_refs_drops_plays_without_a_usable_timestamp_when_bounded():
    refs = [
        {"id": 1},
        {"id": 2, "timestamp": None},
        {"id": 3, "timestamp": "junk"},
        {"id": 4, "timestamp": at(5).isoformat()},
    ]
    assert [r["id"] for r in filter_refs(refs, at(0), None)] == [4]
    assert filter_refs([], at(0), None) == []


# ------------------------------------------------------------------ speed_of
@pytest.mark.parametrize(
    ("meta", "speed"),
    [
        ({}, 1.0),
        ({"rate": None}, 1.0),
        ({"rate": 0}, 1.0),  # a missing rate and a zero rate both mean normal speed
        ({"rate": 1.5}, 1.5),
        ({"rate": "0.75"}, 0.75),
        ({"rate": 1.5004}, 1.5),
        ({"rate": 1.3333333}, 1.333),
    ],
)
def test_speed_of(meta, speed):
    assert speed_of(meta) == speed


# ------------------------------------------------------------------ best_replays / select
def test_best_replays_drops_unfinished_plays():
    assert best_replays([play(completed=False), play(completed=None), {"beatmap_md5": "m1"}]) == []
    assert best_replays([]) == []


def test_best_replays_keeps_the_highest_score_per_map():
    a, b, c = play(score=100), play(score=300), play(score=200)
    assert best_replays([a, b, c]) == [b]


def test_best_replays_breaks_score_ties_by_accuracy():
    a, b = play(score=500, acc=0.95), play(score=500, acc=0.99)
    assert best_replays([a, b]) == [b]
    assert best_replays([b, a]) == [b]


def test_best_replays_full_tie_keeps_the_first_in_input_order():
    a, b = play(score=500, acc=0.9, name="newer"), play(score=500, acc=0.9, name="older")
    assert best_replays([a, b]) == [a]


def test_best_replays_score_beats_accuracy():
    a, b = play(score=900, acc=0.80), play(score=800, acc=0.99)
    assert best_replays([a, b]) == [a]


def test_best_replays_treats_missing_score_and_accuracy_as_zero():
    a, b = play(score=None, acc=None), play(score=1, acc=None)
    assert best_replays([a, b]) == [b]
    assert best_replays([a]) == [a]  # a pass with no score data still counts


def test_best_replays_separates_maps_and_speeds():
    nm = play("m1", 100)
    dt_ = play("m1", 90, rate=1.5)
    other = play("m2", 50)
    near_dt = play("m1", 95, rate=1.5004)  # same speed once rounded
    out = best_replays([nm, dt_, other, near_dt])
    assert sorted(map(id, out)) == sorted(map(id, [nm, near_dt, other]))
    assert len(out) == 3


def test_best_replays_nm_and_missing_rate_are_the_same_speed():
    a, b = play(rate=None, score=1), play(rate=1.0, score=2)
    assert best_replays([a, b]) == [b]


def test_best_replays_unfinished_play_never_replaces_a_pass():
    ok, failed = play(score=100), play(score=9999, completed=False)
    assert best_replays([ok, failed]) == [ok]


def test_best_replays_works_on_objects_with_meta():
    class Analysis:
        def __init__(self, meta):
            self.meta = meta

    a, b = Analysis(play(score=10)), Analysis(play(score=20))
    assert best_replays([a, b]) == [b]
    assert best_replays([a, play(score=30)])[0]["score"] == 30  # plain dicts and objects can be mixed


def test_select_all_returns_every_play_as_a_copy():
    plays = [play(score=1), play(score=2, completed=False)]
    out = select(plays)
    assert out == plays and out is not plays
    assert select(plays, "all") == plays
    assert select(plays, "anything else") == plays


def test_select_best_applies_the_best_filter():
    a, b, c = play(score=1), play(score=2), play(score=3, completed=False)
    assert select([a, b, c], "best") == [b]
