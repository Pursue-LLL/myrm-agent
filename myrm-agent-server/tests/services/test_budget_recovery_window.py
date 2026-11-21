"""The recoveries and the audit count spend from the start of a budget day on the host clock, in any host time zone.

After a restart the recoveries count the spend since today's budget day began; the audit counts the last ``days`` budget
days, today included. Stored messages carry naive UTC times while the guards roll over on the host's local calendar day,
so a window that starts at the wrong instant seeds a guard with yesterday's spend or leaves part of today's out. The
tests put a reply one second before and one second after that instant, read off the host clock, and only the second one
may count.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.budget.router import get_channel_audit
from app.services.budget.channel_budget import _query_channel_today_cost
from app.services.budget.enforcer import _query_today_cost
from tests.support.budget_day_clock import host_day_start_utc, host_timezone
from tests.support.channel_budget_fixtures import budget_database
from tests.support.channel_chat_rows import seed_channel_chat, seed_costed_reply

_GROUP = "telegram:group:g-1"
_YESTERDAY_COST = 4.0
_TODAY_COST = 1.5


@pytest.fixture(autouse=True, params=["UTC", "Asia/Shanghai", "America/Los_Angeles"])
def _host_zone(request: pytest.FixtureRequest, db_session: AsyncSession) -> Iterator[None]:
    with host_timezone(request.param), budget_database(db_session):
        yield


async def _spend_around_day_start(db: AsyncSession, days_ago: int = 0) -> None:
    """Store a reply one second before and one second after the start of the budget day ``days_ago`` days back."""
    start = host_day_start_utc(days_ago)
    chat_id = await seed_channel_chat(db, f"{_GROUP}:e=2026-10-27")
    await seed_costed_reply(db, chat_id, _YESTERDAY_COST, at=start - timedelta(seconds=1))
    await seed_costed_reply(db, chat_id, _TODAY_COST, at=start + timedelta(seconds=1))


@pytest.mark.asyncio
async def test_the_channel_recovery_starts_with_the_budget_day(db_session: AsyncSession) -> None:
    await _spend_around_day_start(db_session)

    assert await _query_channel_today_cost(_GROUP) == pytest.approx(_TODAY_COST)


@pytest.mark.asyncio
async def test_the_global_recovery_starts_with_the_budget_day(db_session: AsyncSession) -> None:
    await _spend_around_day_start(db_session)

    assert await _query_today_cost() == pytest.approx(_TODAY_COST)


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [1, 7, 90])
async def test_the_audit_covers_the_last_days_budget_days_today_included(db_session: AsyncSession, days: int) -> None:
    await _spend_around_day_start(db_session, days_ago=days - 1)

    response = await get_channel_audit(_GROUP, days=days)

    assert json.loads(bytes(response.body))["data"]["total_cost_usd"] == pytest.approx(_TODAY_COST)
