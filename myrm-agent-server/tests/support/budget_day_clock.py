"""Host clock controls shared by the budget day tests: the process time zone, the day the budget code sees, the day start."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, date, datetime
from typing import Self
from unittest.mock import patch

# Every module that reads the host's calendar day to decide where a budget day begins or ends.
_BUDGET_DAY_READERS = (
    "myrm_agent_harness.utils.token_economics.budget_guard",
    "myrm_agent_harness.utils.token_economics.multidim_budget",
    "app.services.budget.budget_day",
)


@contextmanager
def host_timezone(name: str) -> Iterator[None]:
    """Run the process clock in the zone ``name`` (an IANA name), then put the previous zone back."""
    previous = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if previous is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = previous
        time.tzset()


@contextmanager
def budget_today(day: date) -> Iterator[None]:
    """Make ``day`` the host's calendar day for the guards and the recovery windows, whatever the clock says."""

    class _Today(date):
        @classmethod
        def today(cls) -> Self:
            return cls(day.year, day.month, day.day)

    with ExitStack() as stack:
        for module in _BUDGET_DAY_READERS:
            stack.enter_context(patch(f"{module}.date", _Today))
        yield


def host_day_start_utc(days_ago: int = 0) -> datetime:
    """The first instant of the host's calendar day ``days_ago`` days back as naive UTC, read off the clock minute by minute.

    It shares no code with the budget day function, so comparing the two checks that function against the clock.
    """
    probe = int(time.time()) // 60 * 60
    for step in range(days_ago + 1):
        if step:
            probe -= 60  # the last minute of the previous day
        day = date.fromtimestamp(probe)
        while date.fromtimestamp(probe - 60) == day:
            probe -= 60
    return datetime.fromtimestamp(probe, UTC).replace(tzinfo=None)
