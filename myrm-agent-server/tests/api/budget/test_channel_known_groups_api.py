"""The budget API names the groups a chat exists for, and says which budgeted channels have not been seen yet."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.budget import budget_router
from app.services.budget import channel_budget
from app.services.budget.channel_budget import ChannelBudgetRegistry
from app.services.budget.channel_budget_key import group_budget_key
from tests.support.channel_budget_fixtures import GROUP_IDS, budget_database
from tests.support.channel_chat_rows import seed_channel_chat

_KNOWN_GROUPS_URL = "/budget/channels/known-groups"


@pytest.fixture
async def client(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(channel_budget, "_registry", ChannelBudgetRegistry())
    app = FastAPI()
    app.include_router(budget_router, prefix="/budget")
    with budget_database(db_session):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


async def _known_groups(client: AsyncClient) -> list[str]:
    return (await client.get(_KNOWN_GROUPS_URL)).json()["data"]["channel_keys"]


async def _seen_by_channel(client: AsyncClient) -> dict[str, bool]:
    statuses = (await client.get("/budget/channels")).json()["data"]["statuses"]
    return {status["channel_key"]: status["known"] for status in statuses}


async def test_no_group_is_listed_before_a_chat_exists(client: AsyncClient) -> None:
    assert await _known_groups(client) == []


async def test_a_group_is_listed_once_by_the_latest_activity_of_its_chats(client: AsyncClient, db_session: AsyncSession) -> None:
    await seed_channel_chat(db_session, "telegram:group:g-1:e=2026-11-15", idle_minutes=600)
    await seed_channel_chat(db_session, "telegram:group:g-1:e=2026-11-16", idle_minutes=60)
    await seed_channel_chat(db_session, "slack:group:c-2:thread:t9", idle_minutes=5)
    await seed_channel_chat(db_session, "discord:group:d-3", idle_minutes=300)

    assert await _known_groups(client) == ["slack:group:c-2", "telegram:group:g-1", "discord:group:d-3"]


async def test_a_conversation_that_is_not_a_group_is_not_listed(client: AsyncClient, db_session: AsyncSession) -> None:
    await seed_channel_chat(db_session, "telegram:dm:u1")
    await seed_channel_chat(db_session, "slack:dm:u2:thread:group:agent:a1")
    await seed_channel_chat(db_session, "telegram:group:g-1")

    assert await _known_groups(client) == ["telegram:group:g-1"]


@pytest.mark.parametrize(("channel", "peer"), GROUP_IDS)
async def test_an_offered_group_is_taken_as_a_policy_key_unchanged_and_is_seen(
    client: AsyncClient, db_session: AsyncSession, channel: str, peer: str
) -> None:
    key = group_budget_key(channel, peer)
    await seed_channel_chat(db_session, f"{key}:e=2026-11-16")

    assert await _known_groups(client) == [key]
    response = await client.put(f"/budget/channels/{key}", json={})
    assert response.status_code == 200
    assert response.json()["data"]["channel_key"] == key
    assert await _seen_by_channel(client) == {key: True}


async def test_a_channel_is_seen_when_a_chat_continues_its_key_and_not_when_only_a_neighbour_does(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await seed_channel_chat(db_session, "telegram:group:g-10:thread:t1:e=2026-11-16")
    for key in ("telegram:group:g-1", "telegram:group:g-10", "slack:group:never-seen"):
        await client.put(f"/budget/channels/{key}", json={})

    assert await _seen_by_channel(client) == {
        "telegram:group:g-1": False,
        "telegram:group:g-10": True,
        "slack:group:never-seen": False,
    }


async def test_a_failed_lookup_leaves_every_channel_seen_and_is_logged(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    await client.put("/budget/channels/telegram:group:g-1", json={})

    with (
        caplog.at_level(logging.WARNING),
        patch("app.services.budget.channel_budget_groups.get_session_factory", side_effect=RuntimeError("database is down")),
    ):
        response = await client.get("/budget/channels")

    assert response.status_code == 200
    assert [status["known"] for status in response.json()["data"]["statuses"]] == [True]
    assert "Could not tell which budgeted groups have a chat" in caplog.text
