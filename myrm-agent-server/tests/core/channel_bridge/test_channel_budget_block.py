"""Regression tests for channel daily budget block gate (global + per-channel)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.channels.types import InboundMessage
from app.core.channel_bridge.agent_executor.executor import ChannelAgentExecutor


def _inbound_message(*, locale: str = "en", is_group: bool = False) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user-1",
        content="Summarize my inbox",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="chat-1",
        user_id="user-1",
        is_group=is_group,
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


@pytest.mark.asyncio
async def test_channel_budget_block_returns_channel_specific_message() -> None:
    """When global budget is OK but channel budget is exceeded, block with channel message."""
    executor = ChannelAgentExecutor()

    with (
        patch(
            "app.services.budget.enforcer.should_block_execution",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "app.services.budget.channel_budget.should_block_channel",
            return_value=True,
        ),
    ):
        events = [
            event async for event in executor.execute_stream(
                _inbound_message(is_group=True),
            )
        ]

    assert len(events) == 1
    reply = events[0]
    assert "channel" in reply.content.lower() or "频道" in reply.content


@pytest.mark.asyncio
async def test_channel_budget_not_checked_for_dm() -> None:
    """DM messages should skip channel budget check (build_channel_budget_key returns '')."""
    executor = ChannelAgentExecutor()

    with (
        patch(
            "app.services.budget.enforcer.should_block_execution",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "app.services.budget.channel_budget.should_block_channel",
            return_value=True,
        ) as mock_block,
    ):
        events = [
            event async for event in executor.execute_stream(
                _inbound_message(is_group=False),
            )
        ]

    assert len(events) == 1
    assert "budget" in events[0].content.lower()
    mock_block.assert_not_called()
