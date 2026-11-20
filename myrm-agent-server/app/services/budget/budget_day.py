"""Budget day boundary shared by every cost recovery window.

[INPUT]
- none (imports no other project module)

[OUTPUT]
- budget_day_start_utc: Start of a budget day as the naive UTC instant stored message times are compared with

[POS]
Single definition of the budget day on the server. The in-process guards (harness DailyBudgetGuard and
MultidimensionalBudgetGuard) roll over when the host's local calendar day changes, while Message.created_at holds naive
UTC. The cost recovery after a restart and the channel audit start their window here, so they count the day the guards count.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta


def budget_day_start_utc(days_ago: int = 0) -> datetime:
    """Start of the budget day ``days_ago`` calendar days back, as naive UTC.

    Each day's own local midnight is converted (``astimezone`` reads a naive datetime as host local time), so a day
    shortened or lengthened by a clock change still begins at its midnight instead of 24 hours after the previous one.
    """
    day = date.today() - timedelta(days=days_ago)
    return datetime.combine(day, datetime.min.time()).astimezone(UTC).replace(tzinfo=None)
