"""Progress over time: period keys, per-period skill numbers and per-period play statistics.

Skill scores are the Overview's skill ratings (``skill_ratings``: 50 = expected performance at a comfort
level), each period's measured against ONE reference — the comfort level of all of the player's replays, the
one the Overview uses — so periods can be compared: playing better than that level expects shows as a rise.
(Rating each period at its own comfort level would put every period near 50.)

Besides months, weeks and days, every day with plays also gets a *rolling* score: rated over the plays of the
``ROLLING_DAYS`` days up to it. One day's plays are few and swing a lot; the goals chart follows this steadier line,
whose last point is close to the score of all plays a goal starts from.

Star levels (:func:`star_metrics`) are the other engine's numbers: the star rating each skill holds up on, fitted to
the period's plays alone. They need no common reference, so a period's levels change only with its own plays.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Sequence
from typing import NamedTuple

from osu_coach.domain.player import PlaySummary, build_profile_from, comfort
from osu_coach.domain.player.constants import SKILLS
from osu_coach.domain.player.engines import COMFORT, ENGINES, make_engine
from osu_coach.domain.player.records import UNRATED

FEW_PLAYS = 5  # periods with fewer plays are shown, but marked as uncertain
PERIODS = ("month", "week", "day")
ROLLING = "rolling"  # metric key prefix of the rolling day scores ("rolling:YYYY-MM-DD")
ROLLING_DAYS = 7
# Saved with a period's skill scores: the comfort level (★) they were rated at. Its presence also marks scores of
# this rating scale; scores saved by older versions (a miss model) have none and are not shown.
SKILL_REFERENCE = "skill_reference_stars"
HISTORY_ENGINE = COMFORT  # the engine that rates the saved scores
# the engine whose skills are star levels (it measures against the maps, not a level): the saved star levels'
STAR_ENGINE = next(name for name in ENGINES if not make_engine(name).uses_level)
STAR_PREFIX = "stars_"  # metric name prefix of the star levels: stars_<skill>, stars_<skill>_low, stars_<skill>_high


def utc(date) -> dt.datetime:
    if isinstance(date, str):
        date = dt.datetime.fromisoformat(date)
    return date.replace(tzinfo=dt.UTC) if date.tzinfo is None else date


def month_of(date, tz=None) -> str:
    """'YYYY-MM' of a replay date (stored in UTC) in ``tz`` (None: UTC)."""
    return utc(date).astimezone(tz or dt.UTC).strftime("%Y-%m")


def period_of(date, period: str = "month", tz=None) -> str:
    """The period a replay date falls in, in ``tz`` (None: UTC): 'YYYY-MM' (month), 'YYYY-Www' (ISO week) or
    'YYYY-MM-DD'."""
    d = utc(date).astimezone(tz or dt.UTC)
    if period == "day":
        return d.strftime("%Y-%m-%d")
    if period == "week":
        y, w, _ = d.isocalendar()
        return f"{y}-W{w:02d}"
    return d.strftime("%Y-%m")


def metric_key(period: str, key: str) -> str:
    """Months keep their plain key (older databases); days / weeks are 'day:…' / 'week:…'."""
    return key if period == "month" else f"{period}:{key}"


class Metric(NamedTuple):
    """One number of a period: ``n`` is how many map/mod configurations a skill score was measured on (else 0)."""

    name: str
    value: float | None
    n: int


def play_label(
    title: str | None, artist: str | None = None, version: str | None = None, mods: str | None = None
) -> str | None:
    """'Artist - Title [Difficulty] +MODS' of a play (no '+…' without mods); None without a title."""
    title, artist, version, mods = ((v or "").strip() for v in (title, artist, version, mods))
    if not title:
        return None
    label = f"{artist} - {title}" if artist else title
    if version:
        label += f" [{version}]"
    if mods and mods.upper() != "NM":
        label += f" +{mods}"
    return label


def period_metrics(
    plays: Sequence[PlaySummary],
    tz=None,
    *,
    reference: float | None = None,
    periods: Sequence[str] = PERIODS,
    rolling: bool = True,
) -> dict[str, list[Metric] | None]:
    """Skill scores and stream speed per period key (see :func:`metric_key`) as :class:`Metric` rows; for a skill
    ``n`` is how many map/mod configurations it was measured on. ``None`` for a period with too few plays (stale
    numbers should go); periods that can't be analysed are left out. ``plays``: the per-play summaries.

    ``reference``: the comfort level (★) to rate every period at; default: the one of all of ``plays``.
    ``periods`` / ``rolling``: which kinds of period to work out (all of them by default)."""
    analyses = list(plays)
    if not analyses:
        return {}
    if reference is None:  # the Overview's comfort level: one yardstick for every period
        reference = comfort([a.meta for a in analyses]).measured
    out: dict[str, list[Metric] | None] = {}
    for key, group in period_groups(analyses, tz, periods=periods, rolling=rolling).items():
        if len(group) < FEW_PLAYS:  # a play or two say little about a period's skill
            out[key] = None
            continue
        try:
            # level=reference: the ratings are measured against it, not against the period's own comfort
            mp = build_profile_from(
                group,
                level=reference,
                weighted=False,
                with_ratings=reference is not None,
                engine=make_engine(HISTORY_ENGINE),
            )
        except Exception:  # noqa: BLE001 - one period that can't be computed must not stop the others
            continue
        ratings = mp.skill_ratings
        rows = [Metric(f"skill_{k}", ratings.get(k, UNRATED).score, ratings.get(k, UNRATED).maps) for k in SKILLS]
        rows += [
            Metric(SKILL_REFERENCE, reference, 0),
            Metric("stream_bpm", mp.tapping.comfort_bpm, int(mp.tapping.n or 0)),
            Metric("ur_single", mp.tapping.ur_single, 0),
            Metric("aim_err", mp.aim.aim_err_median, 0),
        ]
        out[key] = rows
    return out


def period_groups(
    plays: Sequence[PlaySummary], tz=None, *, periods: Sequence[str] = PERIODS, rolling: bool = True
) -> dict[str, list[PlaySummary]]:
    """The plays of every period key (see :func:`metric_key`): months, ISO weeks and days, and with ``rolling`` each
    day with plays' last ``ROLLING_DAYS`` days."""
    groups = defaultdict(list)
    by_day = defaultdict(list)
    for a in plays:
        for period in periods:  # months, ISO weeks and days, each kept under its own key
            groups[metric_key(period, period_of(a.meta.date, period, tz))].append(a)
        by_day[dt.date.fromisoformat(period_of(a.meta.date, "day", tz))].append(a)
    for day in by_day if rolling else ():  # each day with plays: the plays of the last ROLLING_DAYS days up to it
        first = day - dt.timedelta(days=ROLLING_DAYS - 1)
        groups[metric_key(ROLLING, day.isoformat())] = [
            a for d, items in by_day.items() if first <= d <= day for a in items
        ]
    return dict(groups)


def star_metrics(plays: Sequence[PlaySummary]) -> list[Metric] | None:
    """The star level of each skill fitted to these plays alone (``STAR_ENGINE``), with its 90% range
    (``stars_<skill>``, ``_low``, ``_high``; ``n``: the map/mod configurations it was measured on). None with too
    few plays, or when the fit fails."""
    if len(plays) < FEW_PLAYS:
        return None
    try:
        ratings = build_profile_from(plays, weighted=False, engine=make_engine(STAR_ENGINE)).skill_ratings
    except Exception:  # noqa: BLE001 - one period that can't be fitted must not stop the others
        return None
    out = []
    for k in SKILLS:
        r = ratings.get(k, UNRATED)
        out += [
            Metric(f"{STAR_PREFIX}{k}", r.stars, r.maps),
            Metric(f"{STAR_PREFIX}{k}_low", r.stars_low, 0),
            Metric(f"{STAR_PREFIX}{k}_high", r.stars_high, 0),
        ]
    return out
