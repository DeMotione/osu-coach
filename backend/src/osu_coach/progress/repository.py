"""Progress by month, kept in SQLite (``progress.sqlite`` in the osu-coach data folder).

Every analysed replay is stored as one row (map, stars, accuracy, misses, ...): the history stays even
when replays or the analysis cache are deleted later. Per month and player:

* from those rows: plays, maps (and maps played for the first time), play time, star rating (average,
  comfortable, hardest clean pass / full combo), accuracy, misses, UR;
* from the analyses themselves (months with 5+ plays): skill scores and stream speed. Skill scores are
  measured against ONE miss model fitted on all of the player's replays — 50 = your all-time average at
  that difficulty, more = fewer misses than usual that month — so months can be compared. (The profile's
  own scores compare each skill with the player's level in the same replays, so they can't show progress.)
"""
from __future__ import annotations

import datetime as dt
import math
import sqlite3
from pathlib import Path

import pandas as pd

from osu_coach.config import default_cache_dir
from osu_coach.progress.domain import mark_full_combos, month_of, period_metrics, period_of, summarize_periods, utc

DB_FILE = "progress.sqlite"
SCHEMA_VERSION = 2   # 2: hp, path
# replays table column -> meta key
COLUMNS = {
    "player": "player", "beatmap_md5": "beatmap_md5", "beatmap_id": "beatmap_id", "beatmapset_id": "beatmapset_id",
    "artist": "artist", "title": "title", "version": "version", "creator": "creator", "mods": "mod_string",
    "rate": "rate", "client": "client", "stars": "stars", "aim_stars": "aim", "speed_stars": "speed", "bpm": "bpm",
    "length_s": "length_s", "ar": "ar", "od": "od", "cs": "cs", "accuracy": "accuracy", "n300": "n300",
    "n100": "n100", "n50": "n50", "nmiss": "nmiss", "head_misses": "head_misses", "n_objects": "n_objects",
    "n_played": "n_played", "completed": "completed", "max_combo": "max_combo", "map_max_combo": "map_max_combo",
    "ur": "ur", "score": "score", "hp": "hp", "path": "source_path",
}
TEXT_COLUMNS = ("player", "beatmap_md5", "artist", "title", "version", "creator", "mods", "client", "path")
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS replays (
    key TEXT PRIMARY KEY, played_at TEXT, month TEXT NOT NULL, added_at TEXT,
    {", ".join(f"{c} {'TEXT' if c in TEXT_COLUMNS else 'REAL'}" for c in COLUMNS)}
);
CREATE INDEX IF NOT EXISTS replays_player_month ON replays (player, month);
CREATE TABLE IF NOT EXISTS month_metrics (
    player TEXT NOT NULL, month TEXT NOT NULL, name TEXT NOT NULL, value REAL, n INTEGER, updated_at TEXT,
    PRIMARY KEY (player, month, name)
);
"""

def db_path(cache_dir=None) -> Path:
    return Path(cache_dir or default_cache_dir()) / DB_FILE


def connect(cache_dir=None) -> sqlite3.Connection:
    path = db_path(cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    have = {r[1] for r in conn.execute("PRAGMA table_info(replays)")}
    with conn:   # databases from older versions: add the new columns (filled in when a replay is analysed again)
        for c in COLUMNS:
            if c not in have:
                conn.execute(f"ALTER TABLE replays ADD COLUMN {c} {'TEXT' if c in TEXT_COLUMNS else 'REAL'}")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return conn


def _value(v):
    if v is None or isinstance(v, (str, int)):
        return v
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return None if math.isnan(f) else f


def record(conn: sqlite3.Connection, analyses, tz=None) -> int:
    """Store (or refresh) one row per analysed replay. Returns how many replays were new."""
    before = conn.execute("SELECT COUNT(*) FROM replays").fetchone()[0]
    now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    cols = list(COLUMNS)
    sql = (f"INSERT INTO replays (key, played_at, month, added_at, {', '.join(cols)}) "
           f"VALUES ({', '.join('?' * (len(cols) + 4))}) ON CONFLICT(key) DO UPDATE SET "
           + ", ".join(f"{c} = excluded.{c}" for c in ["played_at", "month"] + cols))
    rows = []
    for a in analyses:
        m = a.meta
        rows.append([a.key, utc(m["date"]).isoformat(), month_of(m["date"], tz), now]
                    + [_value(m.get(COLUMNS[c])) for c in cols])
    with conn:
        conn.executemany(sql, rows)
    return conn.execute("SELECT COUNT(*) FROM replays").fetchone()[0] - before


def saved_plays(conn: sqlite3.Connection, a) -> pd.DataFrame:
    """The saved plays of ``a``'s player on ``a``'s map."""
    return pd.read_sql_query("SELECT * FROM replays WHERE player = ? AND beatmap_md5 = ?", conn,
                             params=(a.meta.get("player") or "", a.meta.get("beatmap_md5")))


def players(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    return [(p or "", n) for p, n in conn.execute(
        "SELECT player, COUNT(*) FROM replays GROUP BY player ORDER BY COUNT(*) DESC, player")]


def rebuild_months(conn: sqlite3.Connection, player: str, analyses, tz=None) -> None:
    """Skill scores (against one model fitted on all of ``analyses``) and stream speed per month."""
    analyses = [a for a in analyses if (a.meta.get("player") or "") == (player or "")]
    now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    for month, rows in period_metrics(analyses, tz).items():
        with conn:
            conn.execute("DELETE FROM month_metrics WHERE player = ? AND month = ?", (player, month))
            if rows:
                conn.executemany("INSERT INTO month_metrics VALUES (?, ?, ?, ?, ?, ?)",
                                 [(player, month, name, _value(value), n, now) for name, value, n in rows])


def update(cache_dir, analyses, load_cached=None, tz=None) -> list[str]:
    """Store new analyses and recompute the months of their players. ``load_cached(keys)`` returns earlier
    analyses (from the analysis cache) for replays stored before but not analysed this time."""
    conn = connect(cache_dir)
    try:
        record(conn, analyses, tz)
        names = sorted({a.meta.get("player") or "" for a in analyses})
        for player in names:
            have = {a.key: a for a in analyses if (a.meta.get("player") or "") == player}
            keys = [k for (k,) in conn.execute("SELECT key FROM replays WHERE player = ?", (player,))]
            older = load_cached([k for k in keys if k not in have]) if load_cached else []
            rebuild_months(conn, player, list(have.values()) + list(older), tz)
        return names
    finally:
        conn.close()


def monthly(conn: sqlite3.Connection, player: str) -> pd.DataFrame:
    """One row per month with plays: counts, star rating, accuracy, skills (``skill_<name>``) etc."""
    return by_period(conn, player, "month")


def by_period(conn: sqlite3.Connection, player: str, period: str = "month", since: dt.date | None = None,
              until: dt.date | None = None, tz=None) -> pd.DataFrame:
    """Like :func:`monthly`, per ``period`` ("month", "week" or "day"; the ``month`` column holds the period's
    key), only plays from ``since`` to ``until`` (dates in ``tz``, both included)."""
    df = pd.read_sql_query("SELECT * FROM replays WHERE player = ?", conn, params=(player,))
    mm = pd.read_sql_query("SELECT month, name, value FROM month_metrics WHERE player = ?", conn,
                           params=(player,))
    return summarize_periods(df, mm, period, since, until, tz)


def month_plays(conn: sqlite3.Connection, player: str, month: str, period: str = "month", tz=None) -> pd.DataFrame:
    """The plays of one month (or of one week / day: ``period`` and its key), newest first."""
    if period == "month":
        df = pd.read_sql_query("SELECT * FROM replays WHERE player = ? AND month = ? ORDER BY played_at DESC",
                               conn, params=(player, month))
    else:
        df = pd.read_sql_query("SELECT * FROM replays WHERE player = ? ORDER BY played_at DESC", conn,
                               params=(player,))
        df = df[[period_of(t, period, tz) == month for t in df["played_at"]]]
    return mark_full_combos(df)
