"""The channel audit endpoint answers a window of 1 to 90 budget days and turns every other length away at the door."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.budget import budget_router
from tests.support.channel_budget_fixtures import budget_database

_AUDIT_URL = "/budget/channels/telegram:group:g-1/audit"


@pytest.fixture
async def audit_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(budget_router, prefix="/budget")
    with budget_database(db_session):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


@pytest.mark.parametrize(("days", "status_code"), [(-1, 422), (0, 422), (1, 200), (90, 200), (91, 422), (10**6, 422)])
async def test_the_audit_window_is_one_to_ninety_budget_days(audit_client: AsyncClient, days: int, status_code: int) -> None:
    response = await audit_client.get(_AUDIT_URL, params={"days": days})

    assert response.status_code == status_code


async def test_the_audit_window_defaults_to_a_week(audit_client: AsyncClient) -> None:
    response = await audit_client.get(_AUDIT_URL)

    assert response.json()["data"]["period_days"] == 7
