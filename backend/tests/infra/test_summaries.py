"""The per-play summaries store (``summaries.sqlite``): what is kept, what is made again, and that a broken store
never stops the analysis."""

from __future__ import annotations

import sqlite3

import pytest

from osu_coach.domain.player import PlaySummary
from osu_coach.infra import summaries
from tests.conftest import play_of


def _play(key: str):
    return play_of({"key": key, "player": "P", "date": "2026-01-01T00:00:00+00:00"})


def _store(tmp_path):
    return tmp_path / summaries.DB_FILE


def _never_loaded(keys):
    raise AssertionError(f"the analysis cache was read for {keys}")


def test_summaries_are_made_once_and_kept(tmp_path):
    made = summaries.summarize(tmp_path, [_play("a"), _play("b")])
    assert [s.key for s in made] == ["a", "b"] and all(isinstance(s, PlaySummary) for s in made)
    assert set(summaries.load(tmp_path, ["a", "b", "c"])) == {"a", "b"}
    assert [s.key for s in summaries.summaries_of(tmp_path, ["b", "a"], _never_loaded)] == ["b", "a"]


def test_missing_summaries_are_made_from_the_analysis_cache_and_stored(tmp_path):
    asked = []

    def load_cached(keys):
        asked.append(list(keys))
        return [_play(k) for k in keys if k != "gone"]

    got = summaries.summaries_of(tmp_path, ["a", "gone", "b"], load_cached)
    assert [s.key for s in got] == ["a", "b"]  # a play found nowhere is left out
    assert asked == [["a", "gone", "b"]]
    assert set(summaries.load(tmp_path, ["a", "b"])) == {"a", "b"}


def test_summaries_of_another_version_are_made_again(tmp_path, monkeypatch):
    summaries.summarize(tmp_path, [_play("a")])
    monkeypatch.setattr(summaries, "VERSION", summaries.VERSION + "-changed")  # e.g. the domain code changed
    assert summaries.load(tmp_path, ["a"]) == {}
    assert [s.key for s in summaries.summaries_of(tmp_path, ["a"], lambda keys: [_play(k) for k in keys])] == ["a"]
    assert set(summaries.load(tmp_path, ["a"])) == {"a"}  # stored again with the new version


@pytest.mark.parametrize("data", [b"not zlib", summaries.zlib.compress(b"not a pickle"), None])
def test_an_unreadable_row_is_made_again(tmp_path, data):
    summaries.summarize(tmp_path, [_play("a")])
    with sqlite3.connect(_store(tmp_path)) as conn:
        conn.execute("UPDATE summaries SET data = ? WHERE key = 'a'", (data,))
    conn.close()
    assert summaries.load(tmp_path, ["a"]) == {}
    assert [s.key for s in summaries.summarize(tmp_path, [_play("a")])] == ["a"]


def test_a_row_that_is_not_a_summary_is_ignored(tmp_path):
    summaries.summarize(tmp_path, [_play("a")])
    other = summaries.zlib.compress(summaries.pickle.dumps({"key": "a"}))
    with sqlite3.connect(_store(tmp_path)) as conn:
        conn.execute("UPDATE summaries SET data = ? WHERE key = 'a'", (other,))
    conn.close()
    assert summaries.load(tmp_path, ["a"]) == {}


def test_a_file_that_is_not_a_database_is_set_aside_and_started_again(tmp_path):
    _store(tmp_path).write_bytes(b"garbage" * 1000)
    made = summaries.summarize(tmp_path, [_play("a")])
    assert [s.key for s in made] == ["a"]
    assert (tmp_path / f"{summaries.DB_FILE}.corrupt").read_bytes() == b"garbage" * 1000  # kept, not deleted
    assert set(summaries.load(tmp_path, ["a"])) == {"a"}


def test_a_second_corrupt_store_does_not_replace_the_first(tmp_path):
    for garbage in (b"first" * 1000, b"second" * 1000):
        _store(tmp_path).write_bytes(garbage)
        summaries.summarize(tmp_path, [_play("a")])
    assert (tmp_path / f"{summaries.DB_FILE}.corrupt").read_bytes() == b"first" * 1000
    assert (tmp_path / f"{summaries.DB_FILE}.corrupt-2").read_bytes() == b"second" * 1000


def test_a_store_that_cant_be_used_still_gives_the_summaries(tmp_path, monkeypatch):
    def locked(cache_dir):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(summaries, "_connect", locked)
    assert [s.key for s in summaries.summarize(tmp_path, [_play("a"), _play("b")])] == ["a", "b"]
    assert [s.key for s in summaries.summaries_of(tmp_path, ["a"], lambda keys: [_play(k) for k in keys])] == ["a"]
    assert not (tmp_path / f"{summaries.DB_FILE}.corrupt").exists()  # a locked store is not set aside


def test_a_corrupt_store_that_cant_be_moved_still_gives_the_summaries(tmp_path, monkeypatch):
    _store(tmp_path).write_bytes(b"garbage" * 1000)

    def cant_move(*args):
        raise PermissionError("in use")

    monkeypatch.setattr(summaries.os, "replace", cant_move)
    assert [s.key for s in summaries.summarize(tmp_path, [_play("a")])] == ["a"]
    assert _store(tmp_path).read_bytes() == b"garbage" * 1000
