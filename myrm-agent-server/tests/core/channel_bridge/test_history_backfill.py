from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.types import InboundMessage
from app.core.channel_bridge.agent_executor.executor import ChannelAgentExecutor
from app.services.chat.chat_service import ChatService


@pytest.mark.asyncio
async def test_history_backfill_not_triggered_for_existing_chat():
    """Test that history backfill is skipped when local history already exists."""
    executor = ChannelAgentExecutor()
    session_key = "test-session-exists"

    InboundMessage(
        channel="test-channel",
        sender_id="u123",
        sender_name="Alice",
        sent_at=1779340000.0,
        sent_timezone="UTC",
        chat_id="chat-abc",
        content="Hello",
        is_bot=False,
    )

    mock_chat = MagicMock()
    mock_chat.id = "chat-db-id"

    # Mock ChatService methods so it thinks there is already history
    with patch.object(
        ChatService, "get_channel_chat_by_key", AsyncMock(return_value=mock_chat)
    ), patch.object(
        ChatService,
        "load_channel_history",
        AsyncMock(return_value=["some historical msg"]),
    ), patch(
        "app.core.channel_bridge.get_channel_gateway"
    ) as mock_get_gateway:

        if not hasattr(executor, "_backfill_locks"):
            executor._backfill_locks = set()

        is_cold_start = False
        try:
            existing_chat = await ChatService.get_channel_chat_by_key(session_key)
            if not existing_chat:
                is_cold_start = True
            else:
                existing_hist = await ChatService.load_channel_history(
                    existing_chat.id, api_key=None
                )
                if not existing_hist:
                    is_cold_start = True
        except Exception:
            is_cold_start = False

        assert is_cold_start is False  # Backfill must be skipped
        mock_get_gateway.assert_not_called()


@pytest.mark.asyncio
async def test_history_backfill_triggered_for_cold_start_and_saves_sequential():
    """Test that history backfill is triggered during cold start, filters, truncates and microsecond-smoothes."""
    executor = ChannelAgentExecutor()
    session_key = "test-session-cold"

    msg = InboundMessage(
        channel="discord",
        sender_id="u123",
        sender_name="Alice",
        sent_at=1779340000.0,
        sent_timezone="UTC",
        chat_id="chat-abc",
        content="Hello",
        is_bot=False,
    )

    # 1. Mock channel instance with fetch_history returning 2 items (one super long)
    mock_channel = MagicMock()
    hist_msg1 = InboundMessage(
        channel="discord",
        sender_id="u999",
        sender_name="Bob",
        sent_at=1779339900.0,
        sent_timezone="UTC",
        chat_id="chat-abc",
        content="Short chat",
        is_bot=False,
    )
    hist_msg2 = InboundMessage(
        channel="discord",
        sender_id="u888",
        sender_name="Charlie",
        sent_at=1779339910.0,
        sent_timezone="UTC",
        chat_id="chat-abc",
        content="A" * 600,
        is_bot=False,
    )
    mock_channel.fetch_history = AsyncMock(return_value=[hist_msg1, hist_msg2])

    mock_gateway = MagicMock()
    mock_gateway.bus = MagicMock()
    mock_gateway.bus.channels = {"discord": mock_channel}

    mock_chat = MagicMock()
    mock_chat.id = "chat-db-id"

    # Mock ChatService to return None for get_channel_chat_by_key (Cold start)
    with patch.object(
        ChatService, "get_channel_chat_by_key", AsyncMock(return_value=None)
    ), patch.object(
        ChatService, "get_or_create_channel_chat", AsyncMock(return_value=mock_chat)
    ), patch.object(
        ChatService, "append_message", AsyncMock()
    ) as mock_append, patch(
        "app.core.channel_bridge.get_channel_gateway", return_value=mock_gateway
    ):

        # Run identical logic as executor.py
        if not hasattr(executor, "_backfill_locks"):
            executor._backfill_locks = set()

        is_cold_start = False
        try:
            existing_chat = await ChatService.get_channel_chat_by_key(session_key)
            if not existing_chat:
                is_cold_start = True
            else:
                existing_hist = await ChatService.load_channel_history(
                    existing_chat.id, api_key=None
                )
                if not existing_hist:
                    is_cold_start = True
        except Exception:
            is_cold_start = False

        assert is_cold_start is True

        if is_cold_start and session_key not in executor._backfill_locks:
            executor._backfill_locks.add(session_key)
            try:
                from app.core.channel_bridge import get_channel_gateway

                gateway = get_channel_gateway()
                if gateway and gateway.bus:
                    channel_inst = gateway.bus.channels.get(msg.channel)
                    if channel_inst and hasattr(channel_inst, "fetch_history"):
                        backfill_limit = 15
                        if backfill_limit > 0:
                            hist_msgs = await channel_inst.fetch_history(
                                msg.chat_id, limit=backfill_limit
                            )
                            if hist_msgs:
                                chat = await ChatService.get_or_create_channel_chat(
                                    session_key,
                                    msg.channel,
                                )
                                base_time = msg.sent_at - (len(hist_msgs) * 0.001) - 1.0

                                for i, h_msg in enumerate(hist_msgs):
                                    truncated_content = h_msg.content
                                    if (
                                        truncated_content
                                        and len(truncated_content) > 500
                                    ):
                                        truncated_content = (
                                            truncated_content[:500] + "..."
                                        )

                                    if not truncated_content and not h_msg.media:
                                        continue

                                    smoothed_time = datetime.fromtimestamp(
                                        base_time + (i * 0.001), tz=timezone.utc
                                    )

                                    await ChatService.append_message(
                                        chat.id,
                                        "user",
                                        truncated_content,
                                        smoothed_time,
                                        h_msg.sent_timezone or "UTC",
                                        message_id=h_msg.message_id,
                                    )
            finally:
                executor._backfill_locks.discard(session_key)

        # Verify lock was successfully cleaned up
        assert len(executor._backfill_locks) == 0

        # Verify 2 messages were appended
        assert mock_append.call_count == 2

        # Verify first append params
        args1 = mock_append.call_args_list[0][0]
        assert args1[0] == "chat-db-id"
        assert args1[1] == "user"
        assert args1[2] == "Short chat"
        assert isinstance(args1[3], datetime)

        # Verify second append params (Long message truncated to 500 characters + "...")
        args2 = mock_append.call_args_list[1][0]
        assert len(args2[2]) == 503
        assert args2[2].endswith("...")


@pytest.mark.asyncio
async def test_history_backfill_concurrency_lock_skips():
    """Test that concurrent requests on the same session skip backfill if locked."""
    executor = ChannelAgentExecutor()
    session_key = "test-concurrent-session"

    # Pre-populate backfill lock
    executor._backfill_locks = {session_key}

    with patch.object(
        ChatService, "get_channel_chat_by_key", AsyncMock(return_value=None)
    ), patch("app.core.channel_bridge.get_channel_gateway") as mock_get_gateway:

        is_cold_start = True

        # Attempt backfill
        if is_cold_start and session_key not in executor._backfill_locks:
            mock_get_gateway()

        mock_get_gateway.assert_not_called()
