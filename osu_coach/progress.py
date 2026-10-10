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
from collections import defaultdict
from pathlib import Path

import pandas as pd

from .profile import SKILL_LABELS, _played, _skills, build_profile, clean_pass, comfort_stars

DB_FILE = "progress.sqlite"
SCHEMA_VERSION = 1
# replays table column -> meta key
COLUMNS = {
    "player": "player", "beatmap_md5": "beatmap_md5", "beatmap_id": "beatmap_id", "beatmapset_id": "beatmapset_id",
    "artist": "artist", "title": "title", "version": "version", "creator": "creator", "mods": "mod_string",
    "rate": "rate", "client": "client", "stars": "stars", "aim_stars": "aim", "speed_stars": "speed", "bpm": "bpm",
    "length_s": "length_s", "ar": "ar", "od": "od", "cs": "cs", "accuracy": "accuracy", "n300": "n300",
    "n100": "n100", "n50": "n50", "nmiss": "nmiss", "head_misses": "head_misses", "n_objects": "n_objects",
    "n_played": "n_played", "completed": "completed", "max_combo": "max_combo", "map_max_combo": "map_max_combo",
    "ur": "ur", "score": "score",
}
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS replays (
    key TEXT PRIMARY KEY, played_at TEXT, month TEXT NOT NULL, added_at TEXT,
    {", ".join(f"{c} {'TEXT' if c in ('player', 'beatmap_md5', 'artist', 'title', 'version', 'creator', 'mods', 'client') else 'REAL'}"
               for c in COLUMNS)}
);
CREATE INDEX IF NOT EXISTS replays_player_month ON replays (player, month);
CREATE TABLE IF NOT EXISTS month_metrics (
    player TEXT NOT NULL, month TEXT NOT NULL, name TEXT NOT NULL, value REAL, n INTEGER, updated_at TEXT,
    PRIMARY KEY (player, month, name)
);
"""
FEW_PLAYS = 5   # months with fewer plays are shown, but marked as uncertain


def db_path(cache_dir=None) -> Path:
    from .library import default_cache_dir
    return Path(cache_dir or default_cache_dir()) / DB_FILE


def connect(cache_dir=None) -> sqlite3.Connection:
    path = db_path(cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return conn


def _utc(date) -> dt.datetime:
    if isinstance(date, str):
        date = dt.datetime.fromisoformat(date)
    return date.replace(tzinfo=dt.timezone.utc) if date.tzinfo is None else date


def month_of(date, tz=None) -> str:
    """'YYYY-MM' of a replay date (stored in UTC) in ``tz`` — default: this computer's time zone."""
    return _utc(date).astimezone(tz).strftime("%Y-%m")


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
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    cols = list(COLUMNS)
    sql = (f"INSERT INTO replays (key, played_at, month, added_at, {', '.join(cols)}) "
           f"VALUES ({', '.join('?' * (len(cols) + 4))}) ON CONFLICT(key) DO UPDATE SET "
           + ", ".join(f"{c} = excluded.{c}" for c in ["played_at", "month"] + cols))
    rows = []
    for a in analyses:
        m = a.meta
        rows.append([a.key, _utc(m["date"]).isoformat(), month_of(m["date"], tz), now]
                    + [_value(m.get(COLUMNS[c])) for c in cols])
    with conn:
        conn.executemany(sql, rows)
    return conn.execute("SELECT COUNT(*) FROM replays").fetchone()[0] - before


def players(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    return [(p or "", n) for p, n in conn.execute(
        "SELECT player, COUNT(*) FROM replays GROUP BY player ORDER BY COUNT(*) DESC, player")]


def rebuild_months(conn: sqlite3.Connection, player: str, analyses, tz=None) -> None:
    """Skill scores (against one model fitted on all of ``analyses``) and stream speed per month."""
    analyses = [a for a in analyses if (a.meta.get("player") or "") == (player or "")]
    if not analyses:
        return
    try:
        full = build_profile(analyses)
    except Exception:  # noqa: BLE001 - too little data for a model
        return
    threshold = full.reading.get("dense_threshold")
    by_month = defaultdict(list)
    for a in analyses:
        by_month[month_of(a.meta["date"], tz)].append(a)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for month, group in by_month.items():
        if len(group) < FEW_PLAYS:   # a play or two say little about a month's skill
            with conn:
                conn.execute("DELETE FROM month_metrics WHERE player = ? AND month = ?", (player, month))
            continue
        try:
            mp = build_profile(group)
            reading = dict(mp.reading)
            if threshold is not None:
                reading["dense_threshold"] = threshold
            skills = _skills(_played(mp.objects), full.model, mp.tapping, mp.sliders, reading, mp.consistency)
        except Exception:  # noqa: BLE001 - a month with too little data keeps no skill numbers
            continue
        rows = [(f"skill_{k}", _value(v.get("score")), int(v.get("n") or 0)) for k, v in skills.items()]
        rows += [("stream_bpm", _value(mp.tapping.get("comfort_bpm")), int(mp.tapping.get("n") or 0)),
                 ("ur_single", _value(mp.tapping.get("ur_single")), 0),
                 ("aim_err", _value(mp.aim.get("aim_err_median")), 0)]
        with conn:
            conn.execute("DELETE FROM month_metrics WHERE player = ? AND month = ?", (player, month))
            conn.executemany("INSERT INTO month_metrics VALUES (?, ?, ?, ?, ?, ?)",
                             [(player, month, name, value, n, now) for name, value, n in rows])


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


def _fc(df: pd.DataFrame) -> pd.Series:
    full = df["map_max_combo"].isna() | (df["max_combo"] >= 0.99 * df["map_max_combo"])
    return df["completed"].astype(bool) & (df["nmiss"] == 0) & full


def monthly(conn: sqlite3.Connection, player: str) -> pd.DataFrame:
    """One row per month with plays: counts, star rating, accuracy, skills (``skill_<name>``) etc."""
    df = pd.read_sql_query("SELECT * FROM replays WHERE player = ?", conn, params=(player,))
    if df.empty:
        return pd.DataFrame(columns=["month", "plays"])
    df["completed"] = df["completed"].fillna(0).astype(bool)
    first = df.groupby("beatmap_md5")["month"].min()
    g = df.groupby("month")
    out = pd.DataFrame({"plays": g.size(), "maps": g["beatmap_md5"].nunique()})
    out["new_maps"] = first.value_counts().reindex(out.index, fill_value=0)
    out["minutes"] = g["length_s"].sum() / 60
    out["notes"] = g["n_played"].sum()
    out["avg_stars"] = g.apply(lambda d: (d["stars"] * d["n_objects"]).sum() / max(d["n_objects"].sum(), 1),
                               include_groups=False)
    out["comfort_stars"] = g.apply(comfort_stars, include_groups=False)
    out["max_stars_passed"] = df[clean_pass(df)].groupby("month")["stars"].max()
    out["max_stars_fc"] = df[_fc(df)].groupby("month")["stars"].max()
    out["accuracy"] = g["accuracy"].mean()
    out["misses_per_100"] = g["head_misses"].sum() / g["n_played"].sum().clip(lower=1) * 100
    out["ur"] = g["ur"].median()
    mm = pd.read_sql_query("SELECT month, name, value FROM month_metrics WHERE player = ?", conn,
                           params=(player,))
    for name in [f"skill_{k}" for k in SKILL_LABELS] + ["stream_bpm", "ur_single", "aim_err"]:
        vals = mm[mm["name"] == name].set_index("month")["value"]
        out[name] = vals.reindex(out.index).astype(float)
    out["few_plays"] = out["plays"] < FEW_PLAYS
    return out.sort_index().reset_index().rename(columns={"index": "month"})


def month_plays(conn: sqlite3.Connection, player: str, month: str) -> pd.DataFrame:
    """The plays of one month, newest first."""
    df = pd.read_sql_query("SELECT * FROM replays WHERE player = ? AND month = ? ORDER BY played_at DESC", conn,
                           params=(player, month))
    df["completed"] = df["completed"].fillna(0).astype(bool)
    df["fc"] = _fc(df)
    return df
