"""Tests for channel approval timeout notification helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.channel_bridge.executor_helpers.approval import notify_channel_timeout_result


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
