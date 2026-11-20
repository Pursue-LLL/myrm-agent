"""The channel budget PATCH endpoint merges the named fields into the stored policy and turns away what it cannot take."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.budget import budget_router
from app.services.budget import channel_budget
from app.services.budget.channel_budget import ChannelBudgetRegistry
from tests.support.channel_budget_fixtures import budget_database

_URL = "/budget/channels/telegram:group:g-1"


@pytest.fixture
async def client(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(channel_budget, "_registry", ChannelBudgetRegistry())
    app = FastAPI()
    app.include_router(budget_router, prefix="/budget")
    with budget_database(db_session):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


async def _stored_policies(client: AsyncClient) -> list[dict[str, object]]:
    return (await client.get("/budget/channels")).json()["data"]["policies"]


async def test_a_patch_changes_the_named_field_and_keeps_the_rest(client: AsyncClient) -> None:
    await client.put(_URL, json={"daily_limit_usd": 5.0, "warning_threshold": 0.6, "label": "Team chat"})

    response = await client.patch(_URL, json={"enabled": False})

    expected = {
        "channel_key": "telegram:group:g-1",
        "daily_limit_usd": 5.0,
        "warning_threshold": 0.6,
        "enabled": False,
        "label": "Team chat",
    }
    assert response.status_code == 200
    assert response.json()["data"] == expected
    assert await _stored_policies(client) == [expected]


async def test_a_patch_of_a_policy_that_does_not_exist_is_a_404_and_creates_nothing(client: AsyncClient) -> None:
    response = await client.patch(_URL, json={"enabled": False})

    assert response.status_code == 404
    assert await _stored_policies(client) == []


@pytest.mark.parametrize(
    ("body", "status_code"),
    [({"channel_key": "slack:group:c1"}, 422), ({"enabled": "maybe"}, 422), ({"daily_limit_usd": 0}, 400)],
)
async def test_a_patch_the_policy_cannot_take_is_turned_away_and_changes_nothing(
    client: AsyncClient, body: dict[str, object], status_code: int
) -> None:
    await client.put(_URL, json={"daily_limit_usd": 5.0})

    response = await client.patch(_URL, json=body)

    assert response.status_code == status_code
    assert [policy["daily_limit_usd"] for policy in await _stored_policies(client)] == [5.0]
