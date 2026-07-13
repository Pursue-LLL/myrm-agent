"""Tests for channel executor helper submodules."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.channel_bridge.executor_helpers.approval import (
    notify_channel_timeout_result,
    schedule_channel_approval_timeout,
)
from app.core.channel_bridge.executor_helpers.history import build_chat_history_with_metadata
from app.core.channel_bridge.executor_helpers.quick_replies import (
    extract_external_agents,
    suggest_quick_replies,
)
from app.services.chat.chat_helpers import ChannelHistoryEntry


@pytest.mark.asyncio
async def test_notify_channel_timeout_result_publishes_with_user_id() -> None:
    with patch(
        "app.core.channel_bridge.channel_gateway.publish",
        new_callable=AsyncMock,
    ) as mock_publish:
        await notify_channel_timeout_result(
            "telegram",
            "chat-42",
            "reject",
            "Done.",
            user_id="user-99",
        )

    mock_publish.assert_awaited_once()
    published = mock_publish.await_args.args[0]
    assert published.channel == "telegram"
    assert published.recipient_id == "chat-42"
    assert published.user_id == "user-99"
    assert "timed out" in published.content.lower()
    assert "Done." in published.content


@pytest.mark.asyncio
async def test_notify_channel_timeout_result_swallows_publish_errors() -> None:
    with patch(
        "app.core.channel_bridge.channel_gateway.publish",
        new_callable=AsyncMock,
        side_effect=RuntimeError("network down"),
    ):
        await notify_channel_timeout_result(
            "telegram",
            "chat-42",
            "approve",
            None,
            user_id="user-99",
        )


def test_schedule_channel_approval_timeout_registers_scheduler() -> None:
    mock_scheduler = MagicMock()
    params = MagicMock()

    with patch(
        "app.core.channel_bridge.executor_helpers.approval.ApprovalTimeoutScheduler.get",
        return_value=mock_scheduler,
    ):
        schedule_channel_approval_timeout(
            channel="telegram",
            peer="chat-1",
            chat_id="chat-db",
            timeout_info={"seconds": 120, "behavior": "deny"},
            params=params,
            user_id="user-1",
        )

    mock_scheduler.schedule.assert_called_once()
    call_kwargs = mock_scheduler.schedule.call_args.kwargs
    assert call_kwargs["key"] == "telegram:chat-1"
    assert call_kwargs["timeout_seconds"] == 120.0
    assert call_kwargs["behavior"] == "deny"
    assert callable(call_kwargs["resume_callback"])


def test_build_chat_history_with_metadata_adds_timestamp_for_human() -> None:
    created = datetime(2026, 7, 13, 6, 0, tzinfo=timezone.utc)
    entries = [
        ChannelHistoryEntry(role="human", content="Hi", created_at=created),
        ChannelHistoryEntry(role="assistant", content="Hello", created_at=created),
    ]

    history = build_chat_history_with_metadata(entries)

    assert history == [
        ["human", "Hi", {"ts": "2026-07-13T06:00:00+00:00"}],
        ["assistant", "Hello"],
    ]


def test_extract_external_agents_returns_none_for_empty() -> None:
    assert extract_external_agents(None) is None
    assert extract_external_agents({}) is None


def test_extract_external_agents_returns_agents_list() -> None:
    agents = [{"id": "a1"}]
    assert extract_external_agents({"agents": agents}) == agents


def test_suggest_quick_replies_only_on_first_message() -> None:
    first = suggest_quick_replies(is_first_message=True)
    later = suggest_quick_replies(is_first_message=False)
    assert len(first) > 0
    assert later == ()
