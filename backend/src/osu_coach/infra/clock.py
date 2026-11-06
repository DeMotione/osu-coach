"""The clock and this computer's time zone: the domain never reads them itself, they are passed in."""

from __future__ import annotations

import datetime as dt


def now() -> dt.datetime:
    """The current time in UTC."""
    return dt.datetime.now(dt.UTC)


def local_tz() -> dt.tzinfo | None:
    """This computer's time zone."""
    return dt.datetime.now().astimezone().tzinfo
