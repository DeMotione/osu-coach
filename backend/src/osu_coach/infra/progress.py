"""Progress by month, kept in SQLite (``progress.sqlite`` in the osu-coach data folder).

Every analysed replay is stored as one row (map, stars, accuracy, misses, ...): the history stays even
when replays or the analysis cache are deleted later. Per month and player:

* from those rows: plays, maps (and maps played for the first time), play time, star rating (average,
  comfortable, hardest clean pass / full combo), accuracy, misses, UR;
* from the analyses themselves (months with 5+ plays): skill scores and stream speed. Skill scores are the
  Overview's skill ratings, every month's measured against ONE reference (the comfort level of all the
  player's replays) so months can be compared; see :mod:`osu_coach.domain.progress.periods`.
"""

from __future__ import annotations

import datetime as dt
import math
import sqlite3
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

import pandas as pd

from osu_coach.config import default_cache_dir
from osu_coach.domain.analysis.models import ReplayMeta
from osu_coach.domain.player import PlaySummary, comfort
from osu_coach.domain.player.constants import SKILLS
from osu_coach.domain.player.levels import CLEAN_PASS_MISSES_PER_100
from osu_coach.domain.progress.periods import (
    FEW_PLAYS,
    ROLLING,
    SKILL_REFERENCE,
    Metric,
    month_of,
    period_metrics,
    period_of,
    play_label,
    utc,
)
from osu_coach.infra import clock

DB_FILE = "progress.sqlite"
SCHEMA_VERSION = 2  # 2: hp, path
# replays table column -> meta key
COLUMNS = {
    "player": "player",
    "beatmap_md5": "beatmap_md5",
    "beatmap_id": "beatmap_id",
    "beatmapset_id": "beatmapset_id",
    "artist": "artist",
    "title": "title",
    "version": "version",
    "creator": "creator",
    "mods": "mod_string",
    "rate": "rate",
    "client": "client",
    "stars": "stars",
    "aim_stars": "aim",
    "speed_stars": "speed",
    "bpm": "bpm",
    "length_s": "length_s",
    "ar": "ar",
    "od": "od",
    "cs": "cs",
    "accuracy": "accuracy",
    "n300": "n300",
    "n100": "n100",
    "n50": "n50",
    "nmiss": "nmiss",
    "head_misses": "head_misses",
    "n_objects": "n_objects",
    "n_played": "n_played",
    "completed": "completed",
    "max_combo": "max_combo",
    "map_max_combo": "map_max_combo",
    "ur": "ur",
    "score": "score",
    "hp": "hp",
    "path": "source_path",
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
    with conn:  # databases from older versions: add the new columns (filled in when a replay is analysed again)
        for c in COLUMNS:
            if c not in have:
                conn.execute(f"ALTER TABLE replays ADD COLUMN {c} {'TEXT' if c in TEXT_COLUMNS else 'REAL'}")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return conn


def _text(v) -> str | None:
    """A text column of a saved play; None for a missing value (None / NaN)."""
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else str(v)


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
    now = clock.now().isoformat(timespec="seconds")
    cols = list(COLUMNS)
    sql = (
        f"INSERT INTO replays (key, played_at, month, added_at, {', '.join(cols)}) "
        f"VALUES ({', '.join('?' * (len(cols) + 4))}) ON CONFLICT(key) DO UPDATE SET "
        + ", ".join(f"{c} = excluded.{c}" for c in ["played_at", "month"] + cols)
    )
    rows = []
    for a in analyses:
        m = a.meta.to_dict()
        rows.append(
            [a.key, utc(m["date"]).isoformat(), month_of(m["date"], tz or clock.local_tz()), now]
            + [_value(m.get(COLUMNS[c])) for c in cols]
        )
    with conn:
        conn.executemany(sql, rows)
    return conn.execute("SELECT COUNT(*) FROM replays").fetchone()[0] - before


def saved_plays(conn: sqlite3.Connection, a) -> pd.DataFrame:
    """The saved plays of ``a``'s player on ``a``'s map."""
    return pd.read_sql_query(
        "SELECT * FROM replays WHERE player = ? AND beatmap_md5 = ?",
        conn,
        params=(a.meta.player, a.meta.beatmap_md5),
    )


def players(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    return [
        (p or "", n)
        for p, n in conn.execute("SELECT player, COUNT(*) FROM replays GROUP BY player ORDER BY COUNT(*) DESC, player")
    ]


def rebuild_months(conn: sqlite3.Connection, player: str, plays: Sequence[PlaySummary], tz=None) -> None:
    """Skill scores (rated at the comfort level of all of the player's ``plays``) and stream speed per month."""
    analyses = [a for a in plays if a.meta.player == (player or "")]
    now = clock.now().isoformat(timespec="seconds")
    for month, rows in period_metrics(analyses, tz or clock.local_tz()).items():
        with conn:
            conn.execute("DELETE FROM month_metrics WHERE player = ? AND month = ?", (player, month))
            if rows:
                conn.executemany(
                    "INSERT INTO month_metrics VALUES (?, ?, ?, ?, ?, ?)",
                    [(player, month, name, _value(value), n, now) for name, value, n in rows],
                )


def update(
    cache_dir,
    analyses: Sequence[PlaySummary],
    load_cached: Callable[[list[str]], Iterable[PlaySummary]] | None = None,
    tz=None,
) -> list[str]:
    """Store new plays and recompute the months of their players. ``load_cached(keys)`` returns the summaries of
    plays stored before but not analysed this time."""
    conn = connect(cache_dir)
    try:
        record(conn, analyses, tz)
        names = sorted({a.meta.player for a in analyses})
        for player in names:
            have = {a.key: a for a in analyses if a.meta.player == player}
            keys = [k for (k,) in conn.execute("SELECT key FROM replays WHERE player = ?", (player,))]
            older = load_cached([k for k in keys if k not in have]) if load_cached else []
            rebuild_months(conn, player, list(have.values()) + list(older), tz)
        return names
    finally:
        conn.close()


def monthly(conn: sqlite3.Connection, player: str) -> pd.DataFrame:
    """One row per month with plays: counts, star rating, accuracy, skills (``skill_<name>``) etc."""
    return by_period(conn, player, "month")


def by_period(
    conn: sqlite3.Connection,
    player: str,
    period: str = "month",
    since: dt.date | None = None,
    until: dt.date | None = None,
    tz=None,
    rolling: bool = False,
    keys=None,
    metrics: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Like :func:`monthly`, per ``period`` ("month", "week" or "day"; the ``month`` column holds the period's
    key), only plays from ``since`` to ``until`` (dates in ``tz``, both included); ``rolling``: see
    :func:`summarize_periods`. ``keys``: only these replays; ``metrics``: skill numbers worked out for them
    (:func:`metrics_frame`) instead of the saved ones."""
    df = pd.read_sql_query("SELECT * FROM replays WHERE player = ?", conn, params=(player,))
    if keys is not None:
        df = df[df["key"].isin(set(keys))]
    mm = (
        metrics
        if metrics is not None
        else pd.read_sql_query("SELECT month, name, value FROM month_metrics WHERE player = ?", conn, params=(player,))
    )
    return summarize_periods(df, mm, period, since, until, tz or clock.local_tz(), rolling=rolling)


def month_plays(
    conn: sqlite3.Connection, player: str, month: str, period: str = "month", tz=None, keys=None
) -> pd.DataFrame:
    """The plays of one month (or of one week / day: ``period`` and its key), newest first; ``keys``: only these."""
    if period == "month":
        df = pd.read_sql_query(
            "SELECT * FROM replays WHERE player = ? AND month = ? ORDER BY played_at DESC", conn, params=(player, month)
        )
    else:
        df = pd.read_sql_query("SELECT * FROM replays WHERE player = ? ORDER BY played_at DESC", conn, params=(player,))
        df = df[[period_of(t, period, tz or clock.local_tz()) == month for t in df["played_at"]]]
    if keys is not None:
        df = df[df["key"].isin(set(keys))]
    return mark_full_combos(df)


def metrics_frame(metrics: dict[str, list[Metric] | None]) -> pd.DataFrame:
    """:func:`~osu_coach.domain.progress.periods.period_metrics` as the (month, name, value) rows
    :func:`summarize_periods` reads (like the saved ``month_metrics`` table)."""
    rows = [(key, m.name, m.value) for key, items in metrics.items() for m in items or ()]
    return pd.DataFrame(rows, columns=["month", "name", "value"])


def full_combo(df: pd.DataFrame) -> pd.Series:
    full = df["map_max_combo"].isna() | (df["max_combo"] >= 0.99 * df["map_max_combo"])
    return df["completed"].astype(bool) & (df["nmiss"] == 0) & full


def summarize_periods(
    df: pd.DataFrame,
    metrics: pd.DataFrame,
    period: str = "month",
    since: dt.date | None = None,
    until: dt.date | None = None,
    tz=None,
    rolling: bool = False,
) -> pd.DataFrame:
    """One row per period with plays: counts, star rating, accuracy, skills (``skill_<name>``) etc.
    ``df``: the player's saved plays; ``metrics``: their month_metrics rows (month, name, value).
    Only plays from ``since`` to ``until`` (dates in ``tz``, both included). ``rolling`` (days only): the skills
    are the rolling scores of the last ``ROLLING_DAYS`` days, or the day's own until those have been saved."""
    if df.empty:
        return pd.DataFrame(columns=["month", "plays"])
    local = pd.to_datetime(df["played_at"], utc=True, format="ISO8601").dt.tz_convert(tz or dt.UTC)
    if since is not None:
        df, local = df[local.dt.date >= since], local[local.dt.date >= since]
    if until is not None:
        df, local = df[local.dt.date <= until], local[local.dt.date <= until]
    if df.empty:
        return pd.DataFrame(columns=["month", "plays"])
    if period != "month":
        df = df.assign(month=[period_of(t.to_pydatetime(), period, tz) for t in local])
    df["completed"] = df["completed"].fillna(0).astype(bool)
    first = df.groupby("beatmap_md5")["month"].min()
    g = df.groupby("month")
    out = pd.DataFrame({"plays": g.size(), "maps": g["beatmap_md5"].nunique()})
    out["new_maps"] = first.value_counts().reindex(out.index, fill_value=0)
    out["minutes"] = g["length_s"].sum() / 60
    out["notes"] = g["n_played"].sum()
    out["avg_stars"] = g.apply(
        lambda d: (d["stars"] * d["n_objects"]).sum() / max(d["n_objects"].sum(), 1), include_groups=False
    )
    out["comfort_stars"] = g.apply(lambda d: comfort(_metas(d)).stars, include_groups=False)
    passed = df[_clean_pass(df)].dropna(subset=["stars"])
    out["max_stars_passed"] = passed.groupby("month")["stars"].max()
    hardest = passed.sort_values(["stars", "played_at"], ascending=[False, False]).drop_duplicates("month")
    out["max_stars_passed_map"] = pd.Series(
        [
            play_label(_text(r["title"]), _text(r["artist"]), _text(r["version"]), _text(r["mods"]))
            for r in hardest.to_dict("records")
        ],
        index=hardest["month"],
        dtype=object,
    ).reindex(out.index)
    out["max_stars_fc"] = df[full_combo(df)].groupby("month")["stars"].max()
    out["accuracy"] = g["accuracy"].mean()
    out["misses_per_100"] = g["head_misses"].sum() / g["n_played"].sum().clip(lower=1) * 100
    out["ur"] = g["ur"].median()
    mm = _keyed(metrics, None if period == "month" else period)
    sm = _keyed(metrics, ROLLING) if rolling and period == "day" else mm
    if (sm["name"] == SKILL_REFERENCE).sum() == 0:  # rolling scores not saved yet (analysed by an older version)
        sm = mm
    rated = set(sm.loc[sm["name"] == SKILL_REFERENCE, "month"])  # skill scores of this rating scale
    for name in [f"skill_{k}" for k in SKILLS] + [SKILL_REFERENCE, "stream_bpm", "ur_single", "aim_err"]:
        src = sm if name.startswith("skill_") else mm
        vals = src[src["name"] == name].set_index("month")["value"]
        if name.startswith("skill_"):
            vals = vals[vals.index.isin(rated)]
        out[name] = vals.reindex(out.index).astype(float)
    out["few_plays"] = out["plays"] < FEW_PLAYS
    return out.sort_index().reset_index().rename(columns={"index": "month"})


def _keyed(metrics: pd.DataFrame, kind: str | None) -> pd.DataFrame:
    """The metric rows of one kind of period (None: months, whose keys have no prefix), keyed without the prefix."""
    if kind is None:
        return metrics[~metrics["month"].str.contains(":")]
    prefix = f"{kind}:"
    return metrics[metrics["month"].str.startswith(prefix)].assign(month=lambda d: d["month"].str[len(prefix) :])


def mark_full_combos(df: pd.DataFrame) -> pd.DataFrame:
    """Plays with ``completed`` as bool and an ``fc`` column."""
    df["completed"] = df["completed"].fillna(0).astype(bool)
    df["fc"] = full_combo(df)
    return df


def _metas(rows: pd.DataFrame) -> list[ReplayMeta]:
    """Saved play rows as replay metas (only the fields the comfort level reads matter)."""
    return [
        ReplayMeta.from_dict({k: v for k, v in r.items() if not (isinstance(v, float) and math.isnan(v))})
        for r in rows.to_dict("records")
    ]


def _clean_pass(df: pd.DataFrame) -> pd.Series:
    """Finished plays with at most 5 misses per 100 notes (:func:`~osu_coach.domain.player.levels.clean_pass`)."""
    per_100 = df["head_misses"] / df["n_objects"].clip(lower=1) * 100
    return df["completed"].astype(bool) & (per_100 <= CLEAN_PASS_MISSES_PER_100)
