"""Which replays go into an analysis: a date window (last session / 7 days / 30 days / custom range) and
"All replays" vs "Best replays".

* **Date window**: on the replay headers (``timestamp``, ISO, UTC), before anything is analysed.
  "Last session" = the newest replay and every replay before it with less than ``SESSION_GAP``
  between consecutive plays.
* **Best replays**: after the analysis (it needs to know whether a play was passed): only passed plays
  (every note reached, no fail), and for every beatmap + speed (NM / DT / HT / custom rate) only the
  single best play — highest score, ties broken by accuracy.
"""
from __future__ import annotations

import datetime as dt

DATE_CHOICES = ["all", "session", "7d", "30d", "custom"]
DATE_LABELS = {"all": "All time", "session": "Last session", "7d": "Last 7 days", "30d": "Last 30 days",
               "custom": "Custom range"}
REPLAY_SETS = ["all", "best"]
REPLAY_SET_LABELS = {"all": "All replays", "best": "Best replays"}
BEST_DEFINITION = ("Best replays = only passed plays (no fails), and for every beatmap + speed mod (NM, DT/NC, HT, "
                   "custom rate) only your single best play: highest score, ties broken by accuracy.")
SESSION_GAP = dt.timedelta(hours=1)


def parse_time(v) -> dt.datetime | None:
    """A replay time (header ISO string or datetime) as an aware UTC datetime."""
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        t = v
    else:
        try:
            t = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except ValueError:
            return None
    return t.replace(tzinfo=dt.timezone.utc) if t.tzinfo is None else t.astimezone(dt.timezone.utc)


def last_session_start(times, gap: dt.timedelta = SESSION_GAP) -> dt.datetime | None:
    """Start of the newest session: walk back from the newest play while plays are less than ``gap`` apart."""
    ts = sorted((t for t in map(parse_time, times) if t is not None), reverse=True)
    if not ts:
        return None
    start = ts[0]
    for t in ts[1:]:
        if start - t > gap:
            break
        start = t
    return start


def date_window(choice: str, times=(), start: dt.date | None = None, end: dt.date | None = None,
                now: dt.datetime | None = None, tz=None) -> tuple[dt.datetime | None, dt.datetime | None]:
    """(since, until) in UTC for a date choice; None = open end. ``times``: replay times (for "session");
    ``start`` / ``end``: dates of a custom range (local calendar days in ``tz``, both included);
    "7d" / "30d" count back from ``now``."""
    now = parse_time(now) if now is not None else dt.datetime.now(dt.timezone.utc)
    if choice == "session":
        return last_session_start(times), None
    if choice == "7d":
        return now - dt.timedelta(days=7), None
    if choice == "30d":
        return now - dt.timedelta(days=30), None
    if choice == "custom":
        tz = tz or dt.datetime.now().astimezone().tzinfo
        since = dt.datetime.combine(start, dt.time.min, tz).astimezone(dt.timezone.utc) if start else None
        until = (dt.datetime.combine(end, dt.time.min, tz) + dt.timedelta(days=1)).astimezone(dt.timezone.utc) \
            if end else None
        return since, until
    return None, None


def in_window(t, since: dt.datetime | None, until: dt.datetime | None) -> bool:
    t = parse_time(t)
    if t is None:
        return since is None and until is None
    return (since is None or t >= since) and (until is None or t < until)


def filter_refs(refs: list[dict], since: dt.datetime | None, until: dt.datetime | None) -> list[dict]:
    """Replay headers (``timestamp``) played inside [since, until)."""
    if since is None and until is None:
        return list(refs)
    return [r for r in refs if in_window(r.get("timestamp"), since, until)]


def speed_of(meta: dict) -> float:
    return round(float(meta.get("rate") or 1.0), 3)


def best_replays(analyses: list) -> list:
    """Best replays (see the module docstring), newest first among equals; works on ReplayAnalysis
    objects (``.meta``) or plain meta dicts."""
    best: dict = {}
    for a in analyses:
        m = a.meta if hasattr(a, "meta") else a
        if not m.get("completed"):
            continue
        key = (m.get("beatmap_md5"), speed_of(m))
        rank = (m.get("score") or 0, m.get("accuracy") or 0.0)
        cur = best.get(key)
        if cur is None or rank > cur[0]:
            best[key] = (rank, a)
    return [a for _, a in best.values()]


def select(analyses: list, replay_set: str = "all") -> list:
    return best_replays(analyses) if replay_set == "best" else list(analyses)
