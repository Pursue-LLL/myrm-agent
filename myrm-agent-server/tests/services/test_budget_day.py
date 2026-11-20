"""The budget day is the host's local calendar day, expressed as the naive UTC instant at which it begins.

The in-process guards roll over when ``date.today()`` changes and stored message times are naive UTC. Every recovery
window starts where ``budget_day_start_utc`` says the day began, so these tests pin the guards, the function and the host
clock to one another: a guard moved to another day boundary, or a window computed in the wrong clock, turns them red.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from myrm_agent_harness.utils.token_economics.budget_guard import DailyBudgetGuard
from myrm_agent_harness.utils.token_economics.multidim_budget import BudgetDimension, MultidimensionalBudgetGuard

from app.services.budget.budget_day import budget_day_start_utc
from tests.support.budget_day_clock import budget_today, host_day_start_utc, host_timezone


def test_the_guards_roll_over_on_the_host_calendar_day() -> None:
    with budget_today(date(2026, 6, 1)):
        daily = DailyBudgetGuard(daily_budget_usd=10.0, initial_cost=3.0)
        multidimensional = MultidimensionalBudgetGuard(daily=BudgetDimension(limit_usd=10.0), initial_daily_cost=3.0)
        assert (daily.today_cost, multidimensional.daily_cost) == (3.0, 3.0)

    with budget_today(date(2026, 6, 2)):
        assert (daily.today_cost, multidimensional.daily_cost) == (0.0, 0.0)


@pytest.mark.parametrize(
    ("zone", "day", "starts_at"),
    [
        ("UTC", date(2026, 6, 1), datetime(2026, 6, 1, 0, 0)),
        ("Asia/Shanghai", date(2026, 6, 1), datetime(2026, 5, 31, 16, 0)),
        # The day the clocks go forward is 23 hours long, the day they go back 25.
        ("America/Los_Angeles", date(2026, 3, 8), datetime(2026, 3, 8, 8, 0)),
        ("America/Los_Angeles", date(2026, 3, 9), datetime(2026, 3, 9, 7, 0)),
        ("America/Los_Angeles", date(2026, 11, 1), datetime(2026, 11, 1, 7, 0)),
        ("America/Los_Angeles", date(2026, 11, 2), datetime(2026, 11, 2, 8, 0)),
    ],
)
def test_the_budget_day_starts_at_local_midnight_as_utc(zone: str, day: date, starts_at: datetime) -> None:
    with host_timezone(zone), budget_today(day):
        assert budget_day_start_utc() == starts_at


def test_days_back_count_calendar_days_not_blocks_of_24_hours() -> None:
    with host_timezone("America/Los_Angeles"), budget_today(date(2026, 3, 9)):
        assert budget_day_start_utc(days_ago=1) == datetime(2026, 3, 8, 8, 0)
        assert budget_day_start_utc(days_ago=7) == datetime(2026, 3, 2, 8, 0)


@pytest.mark.parametrize(
    "zone", ["UTC", "Asia/Shanghai", "Asia/Kolkata", "Europe/Berlin", "America/Los_Angeles", "Australia/Lord_Howe"]
)
def test_the_budget_day_starts_when_the_host_clock_changes_day(zone: str) -> None:
    with host_timezone(zone):
        assert budget_day_start_utc() == host_day_start_utc()
        assert budget_day_start_utc(days_ago=3) == host_day_start_utc(days_ago=3)
