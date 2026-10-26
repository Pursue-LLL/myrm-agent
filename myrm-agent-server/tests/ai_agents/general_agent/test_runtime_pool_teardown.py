"""Per-turn teardown of an ephemeral external-agent pool is bounded; registry pools are only released."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai_agents.general_agent.agent import GeneralAgent
from app.services.external_agents import runtime_pool_registry


async def _hang_forever() -> None:
    await asyncio.Event().wait()


def _agent_with_pool(pool: MagicMock, *, ephemeral: bool, scope_id: str | None) -> GeneralAgent:
    agent = GeneralAgent.__new__(GeneralAgent)
    agent._runtime_pool = pool
    agent._runtime_pool_scope_id = scope_id
    agent._runtime_pool_from_registry = not ephemeral
    agent._runtime_pool_ephemeral = ephemeral
    agent._executor = None
    agent._current_chat_id = None
    agent._browser_spaces = {}
    agent._browser_session = None
    agent.agent = None
    return agent


@pytest.mark.asyncio
@pytest.mark.parametrize("teardown", ["release_pooled_session", "close"])
async def test_ephemeral_pool_teardown_is_bounded_when_backend_hangs(monkeypatch: pytest.MonkeyPatch, teardown: str) -> None:
    monkeypatch.setattr(runtime_pool_registry, "_POOL_CLOSE_TIMEOUT_SECONDS", 0.05)
    pool = MagicMock()
    pool.close_all = AsyncMock(side_effect=_hang_forever)
    agent = _agent_with_pool(pool, ephemeral=True, scope_id=None)

    await asyncio.wait_for(getattr(agent, teardown)(), timeout=2.0)

    pool.close_all.assert_awaited_once()
    assert agent._runtime_pool is None


@pytest.mark.asyncio
@pytest.mark.parametrize("teardown", ["release_pooled_session", "close"])
async def test_registry_pool_teardown_only_releases_and_never_closes(teardown: str) -> None:
    pool = MagicMock()
    pool.close_all = AsyncMock()
    agent = _agent_with_pool(pool, ephemeral=False, scope_id="chat-release")

    await getattr(agent, teardown)()

    pool.close_all.assert_not_called()
    assert agent._runtime_pool is None
