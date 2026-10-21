"""Channel bind policy on AGENT_ROUTE one-shot routing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.routing.router import AgentRouter
from app.channels.types import InboundMessage


def _dm_msg(*, metadata: dict[str, object] | None = None) -> InboundMessage:
    return InboundMessage(
        channel="test",
        sender_id="u1",
        chat_id="c1",
        content="hello",
        user_id="test-user",
        metadata=metadata or {},
    )


@pytest.mark.asyncio
async def test_prepare_execution_rejects_search_route_agent_id() -> None:
    bus = MagicMock()
    router = AgentRouter(bus, MagicMock(), MagicMock())
    router._resolve_topic = AsyncMock(return_value=None)

    search_agent = MagicMock(metadata={"prompt_mode": "search"})
    with patch(
        "app.services.agent.agent_service.AgentService.get_agent_by_id",
        new_callable=AsyncMock,
        return_value=search_agent,
    ):
        ctx = await router._prepare_execution_context(
            _dm_msg(metadata={"route_agent_id": "builtin-fast-search"}),
        )

    assert ctx is not None
    assert ctx.topic_ctx is None


@pytest.mark.asyncio
async def test_prepare_execution_allows_external_cli_route_agent_id() -> None:
    bus = MagicMock()
    router = AgentRouter(bus, MagicMock(), MagicMock())
    router._resolve_topic = AsyncMock(return_value=None)

    with patch(
        "app.services.agent.agent_service.AgentService.get_agent_by_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        ctx = await router._prepare_execution_context(
            _dm_msg(metadata={"route_agent_id": "claude"}),
        )

    assert ctx is not None
    assert ctx.topic_ctx is not None
    assert ctx.topic_ctx.agent_id == "claude"
    assert ctx.topic_ctx.matched_by == "alias"
