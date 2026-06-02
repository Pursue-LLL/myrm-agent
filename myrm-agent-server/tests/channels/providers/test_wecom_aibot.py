import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.providers.wecom.aibot_channel import (
    _MAX_TEXT_LENGTH,
    WeComAiBotChannel,
    WeComStreamState,
)
from app.channels.types import OutboundMessage


@pytest.fixture
def channel():
    c = WeComAiBotChannel(bot_id="test_bot", secret="test_secret")
    yield c
    if c._stream_guardian_task:
        c._stream_guardian_task.cancel()
    c._active_streams.clear()


@pytest.mark.asyncio
async def test_send_placeholder_creates_state(channel):
    channel._ws = AsyncMock()
    stream_id = await channel.send_placeholder("chat_1", "Thinking...", thread_id="req_1")

    assert stream_id is not None
    assert stream_id in channel._active_streams
    state = channel._active_streams[stream_id]
    assert state.chat_id == "chat_1"
    assert state.req_id == "req_1"
    assert state.last_full_text == "Thinking..."
    assert not state.is_force_closed

    channel._ws.send.assert_called_once()
    sent_frame = json.loads(channel._ws.send.call_args[0][0])
    assert sent_frame["cmd"] == "aibot_respond_msg"
    assert sent_frame["body"]["stream"]["content"] == "Thinking..."
    assert sent_frame["body"]["stream"]["finish"] is False


@pytest.mark.asyncio
async def test_edit_message_updates_state(channel):
    channel._ws = AsyncMock()
    stream_id = "stream_1"
    channel._active_streams[stream_id] = WeComStreamState(
        stream_id=stream_id, chat_id="chat_1", req_id="req_1", last_full_text="Old"
    )

    await channel.edit_message("chat_1", stream_id, "New text")

    state = channel._active_streams[stream_id]
    assert state.last_full_text == "New text"
    channel._ws.send.assert_called_once()


@pytest.mark.asyncio
async def test_edit_placeholder_message_normal_closure(channel):
    channel._ws = AsyncMock()
    stream_id = "stream_1"
    channel._active_streams[stream_id] = WeComStreamState(
        stream_id=stream_id, chat_id="chat_1", req_id="req_1", last_full_text="Old"
    )
    msg = OutboundMessage(channel="wecom_aibot", recipient_id="chat_1", user_id="user_1", content="Final answer")

    await channel.edit_placeholder_message("chat_1", stream_id, msg)

    assert stream_id not in channel._active_streams
    channel._ws.send.assert_called_once()
    sent_frame = json.loads(channel._ws.send.call_args[0][0])
    assert sent_frame["cmd"] == "aibot_respond_msg"
    assert sent_frame["body"]["stream"]["finish"] is True


@pytest.mark.asyncio
async def test_edit_placeholder_message_fallback_routing(channel):
    channel._ws = AsyncMock()
    msg = OutboundMessage(channel="wecom_aibot", recipient_id="wr_group_1", user_id="user_1", content="Final group answer")

    # State is None (fallback scenario for groups)
    await channel.edit_placeholder_message("wr_group_1", "lost_stream", msg)

    channel._ws.send.assert_called_once()
    sent_frame = json.loads(channel._ws.send.call_args[0][0])
    assert sent_frame["cmd"] == "aibot_send_msg"
    assert sent_frame["body"]["chat_type"] == 1  # Inferred as group

    # Single chat routing test
    channel._ws.reset_mock()
    await channel.edit_placeholder_message("user_123", "lost_stream", msg)
    channel._ws.send.assert_called_once()
    sent_frame = json.loads(channel._ws.send.call_args[0][0])
    assert sent_frame["cmd"] == "aibot_send_msg"
    assert sent_frame["body"]["chat_type"] == 0  # Inferred as single


@pytest.mark.asyncio
async def test_guardian_loop_20s_jitter(channel):
    channel._ws = AsyncMock()
    stream_id = "stream_1"
    now = time.time()

    channel._active_streams[stream_id] = WeComStreamState(
        stream_id=stream_id, chat_id="chat_1", req_id="req_1",
        start_time=now - 25, last_update_time=now - 25, last_full_text="Thinking..."
    )

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        await channel._stream_keepalive_loop()

    channel._ws.send.assert_called_once()
    sent_frame = json.loads(channel._ws.send.call_args[0][0])
    assert sent_frame["cmd"] == "aibot_respond_msg"
    assert sent_frame["body"]["stream"]["finish"] is False
    assert sent_frame["body"]["stream"]["content"].startswith("Thinking...")


@pytest.mark.asyncio
async def test_guardian_loop_280s_truncation(channel):
    channel._ws = AsyncMock()
    stream_id = "stream_1"
    now = time.time()

    long_text = "A" * 19995
    channel._active_streams[stream_id] = WeComStreamState(
        stream_id=stream_id, chat_id="chat_1", req_id="req_1",
        start_time=now - 285, last_update_time=now - 285, last_full_text=long_text
    )

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        await channel._stream_keepalive_loop()

    state = channel._active_streams.get(stream_id)
    assert state is not None
    assert state.is_force_closed is True

    channel._ws.send.assert_called_once()
    sent_frame = json.loads(channel._ws.send.call_args[0][0])
    assert sent_frame["cmd"] == "aibot_respond_msg"
    assert sent_frame["body"]["stream"]["finish"] is True
    sent_content = sent_frame["body"]["stream"]["content"]
    assert len(sent_content) <= _MAX_TEXT_LENGTH
    assert "处理时间较长" in sent_content


@pytest.mark.asyncio
async def test_guardian_loop_3600s_ttl(channel):
    stream_id = "stream_1"
    now = time.time()

    channel._active_streams[stream_id] = WeComStreamState(
        stream_id=stream_id, chat_id="chat_1", req_id="req_1",
        start_time=now - 3601, last_update_time=now - 3601
    )

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        await channel._stream_keepalive_loop()

    assert stream_id not in channel._active_streams
