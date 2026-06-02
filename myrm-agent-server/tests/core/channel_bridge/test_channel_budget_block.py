"""Regression tests for channel daily budget block gate."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.channels.types import InboundMessage
from app.core.channel_bridge.agent_executor.executor import ChannelAgentExecutor


def _inbound_message(*, locale: str = "en") -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user-1",
        content="Summarize my inbox",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="chat-1",
        user_id="user-1",
        is_group=False,
        mentioned=False,
        metadata={"locale": locale},
    )


@pytest.mark.asyncio
async def test_execute_stream_replies_with_daily_budget_blocked_message() -> None:
    executor = ChannelAgentExecutor()

    with patch(
        "app.services.budget.enforcer.should_block_execution",
        new_callable=AsyncMock,
        return_value=True,
    ):
        events = [event async for event in executor.execute_stream(_inbound_message())]

    assert len(events) == 1
    reply = events[0]
    assert "budget" in reply.content.lower()


@pytest.mark.asyncio
async def test_execute_stream_uses_localized_daily_budget_blocked_message() -> None:
    executor = ChannelAgentExecutor()

    with patch(
        "app.services.budget.enforcer.should_block_execution",
        new_callable=AsyncMock,
        return_value=True,
    ):
        events = [event async for event in executor.execute_stream(_inbound_message(locale="zh-CN"))]

    assert len(events) == 1
    assert "预算" in events[0].content
