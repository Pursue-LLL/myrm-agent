"""A channel budget counts the spend of its own conversation, not of a peer whose key starts the same way.

The budget key of a group is ``{channel}:{peer_kind}:{peer}``; the chats of that group are stored under it with an epoch,
topic or agent appended. ``g-1`` and ``g-10`` are two groups, and ``g_1`` must not match ``gx1``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.budget.router import get_channel_audit
from app.services.budget.channel_budget import _query_channel_today_cost
from tests.support.channel_chat_rows import seed_channel_chat, seed_costed_reply

_GROUP = "telegram:group:g-1"


@pytest.fixture(autouse=True)
def _database(db_session: AsyncSession) -> Iterator[None]:
    @asynccontextmanager
    async def session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    def factory() -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
        return session

    with (
        patch("app.services.budget.channel_budget.get_session_factory", factory),
        patch("app.platform_utils.get_session_factory", factory),
    ):
        yield


async def _spend(db: AsyncSession, key: str, cost_usd: float) -> None:
    await seed_costed_reply(db, await seed_channel_chat(db, key), cost_usd)


@pytest.mark.asyncio
async def test_the_spend_of_every_chat_of_the_group_is_counted(db_session: AsyncSession) -> None:
    await _spend(db_session, f"{_GROUP}:e=2026-10-27", 0.25)
    await _spend(db_session, f"{_GROUP}:thread:t1:e=2026-10-27", 0.5)
    await _spend(db_session, f"{_GROUP}:agent:a1", 1.0)

    assert await _query_channel_today_cost(_GROUP) == pytest.approx(1.75)


@pytest.mark.asyncio
@pytest.mark.parametrize("neighbour", ["telegram:group:g-10:e=2026-10-27", "telegram:group:g-1x"])
async def test_the_spend_of_another_group_is_not_counted(db_session: AsyncSession, neighbour: str) -> None:
    await _spend(db_session, f"{_GROUP}:e=2026-10-27", 0.25)
    await _spend(db_session, neighbour, 5.0)

    assert await _query_channel_today_cost(_GROUP) == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_an_underscore_in_the_group_id_matches_only_itself(db_session: AsyncSession) -> None:
    await _spend(db_session, "telegram:group:g_1:e=2026-10-27", 0.25)
    await _spend(db_session, "telegram:group:gx1:e=2026-10-27", 5.0)

    assert await _query_channel_today_cost("telegram:group:g_1") == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_the_audit_of_a_group_lists_only_its_own_spend(db_session: AsyncSession) -> None:
    await _spend(db_session, f"{_GROUP}:e=2026-10-27", 0.25)
    await _spend(db_session, "telegram:group:g-10:e=2026-10-27", 5.0)

    response = await get_channel_audit(_GROUP)

    assert json.loads(bytes(response.body))["data"]["total_cost_usd"] == pytest.approx(0.25)
