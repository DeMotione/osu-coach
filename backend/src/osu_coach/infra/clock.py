"""The clock and this computer's time zone: the only place that reads them (tests pin :func:`now`); the domain
never reads them itself, they are passed in."""

from __future__ import annotations

import datetime as dt


def now() -> dt.datetime:
    """The current time in UTC."""
    return dt.datetime.now(dt.UTC)


def timestamp() -> float:
    """The current time in seconds since the epoch, like file modification times."""
    return now().timestamp()


def today() -> dt.date:
    """Today's date on this computer."""
    return now().astimezone().date()


def local_tz() -> dt.tzinfo | None:
    """This computer's time zone."""
    return dt.datetime.now().astimezone().tzinfo
