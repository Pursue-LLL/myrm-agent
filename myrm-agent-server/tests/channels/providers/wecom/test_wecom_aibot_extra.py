import asyncio
import json
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.providers.wecom.aibot_channel import WeComAiBotChannel
from app.channels.types import OutboundMessage
from app.channels.types.status import ChannelStatus


@pytest.fixture
def channel() -> Iterator[WeComAiBotChannel]:
    c = WeComAiBotChannel(bot_id="test_bot", secret="test_secret")
    yield c
    if c._stream_guardian_task:
        c._stream_guardian_task.cancel()
    c._active_streams.clear()


@pytest.mark.asyncio
async def test_start_stop(channel: WeComAiBotChannel) -> None:
    await channel.start()
    running = channel._status
    assert running == ChannelStatus.RUNNING
    assert channel._ws_task is not None
    assert channel._stream_guardian_task is not None
    await channel.stop()
    stopped = channel._status
    assert stopped == ChannelStatus.STOPPED
    assert channel._ws_task is None
    assert channel._stream_guardian_task is None


@pytest.mark.asyncio
async def test_health_check_and_issues() -> None:
    c = WeComAiBotChannel("", "")
    issues = c.collect_issues()
    assert any("Bot ID is not configured" in i.message for i in issues)
    assert any("Secret is not configured" in i.message for i in issues)
    assert await c.health_check() is False


@pytest.mark.asyncio
async def test_parse_msg_item(channel: WeComAiBotChannel) -> None:
    content, media = channel._parse_msg_item({"msgtype": "text", "text": {"content": "hello"}})
    assert content == "hello"
    assert media is None

    content, media = channel._parse_msg_item({"msgtype": "image", "image": {"url": "http://img"}})
    assert media is not None
    assert media.media_type.name == "IMAGE"
    assert media.url == "http://img"


@pytest.mark.asyncio
async def test_parse_msg_item_others(channel: WeComAiBotChannel) -> None:
    _, m = channel._parse_msg_item({"msgtype": "file", "file": {"filename": "test.txt"}})
    assert m is not None
    assert m.media_type.name == "DOCUMENT"
    assert m.filename == "test.txt"

    _, m = channel._parse_msg_item({"msgtype": "voice"})
    assert m is not None
    assert m.media_type.name == "AUDIO"

    _, m = channel._parse_msg_item({"msgtype": "video"})
    assert m is not None
    assert m.media_type.name == "VIDEO"

    c, _ = channel._parse_msg_item({"msgtype": "location", "location": {"latitude": "1", "longitude": "2", "label": "place"}})
    assert "place" in c

    c, _ = channel._parse_msg_item({"msgtype": "link", "link": {"title": "Google", "url": "g.com"}})
    assert "Google" in c


@pytest.mark.asyncio
async def test_parse_quoted_message(channel: WeComAiBotChannel) -> None:
    quote = {
        "msgtype": "mixed",
        "msgid": "msg1",
        "mixed": {"msg_item": [{"msgtype": "text", "text": {"content": "quoted text"}}]},
    }
    res = channel._parse_quoted_message({"quote": quote})
    assert res is not None
    assert res.content == "quoted text"


@pytest.mark.asyncio
async def test_handle_msg_callback(channel: WeComAiBotChannel) -> None:
    frame: dict[str, object] = {
        "cmd": "aibot_msg_callback",
        "headers": {"req_id": "r1"},
        "body": {
            "msgid": "m1",
            "chattype": "single",
            "chatid": "c1",
            "from": {"userid": "u1"},
            "msgtype": "text",
            "text": {"content": "hello"},
        },
    }
    with patch.object(channel, "_emit_inbound", new_callable=AsyncMock) as mock_emit:
        await channel._handle_frame(frame)
        mock_emit.assert_called_once()
        msg = mock_emit.call_args[0][0]
        assert msg.content == "hello"
        assert msg.sender_id == "u1"


@pytest.mark.asyncio
async def test_handle_event_callback(channel: WeComAiBotChannel) -> None:
    frame: dict[str, object] = {
        "cmd": "aibot_event_callback",
        "headers": {"req_id": "r1"},
        "body": {"event": {"eventtype": "enter_chat"}, "from": {"userid": "u1"}, "msgid": "m1"},
    }
    with patch.object(channel, "_emit_inbound", new_callable=AsyncMock) as mock_emit:
        await channel._handle_frame(frame)
        mock_emit.assert_called_once()
        msg = mock_emit.call_args[0][0]
        assert msg.sender_id == "u1"
        assert msg.metadata["event_type"] == "enter_chat"


@pytest.mark.asyncio
async def test_subscribe_success(channel: WeComAiBotChannel) -> None:
    ws_mock = AsyncMock()
    ws_mock.recv.return_value = json.dumps({"body": {"ret_code": 0}})
    res = await channel._subscribe(ws_mock)
    assert res is True
    ws_mock.send.assert_called_once()


@pytest.mark.asyncio
async def test_subscribe_fail(channel: WeComAiBotChannel) -> None:
    ws_mock = AsyncMock()
    ws_mock.recv.return_value = json.dumps({"body": {"ret_code": 1}})
    res = await channel._subscribe(ws_mock)
    assert res is False


@pytest.mark.asyncio
async def test_heartbeat_loop(channel: WeComAiBotChannel) -> None:
    ws_mock = AsyncMock()
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        await channel._heartbeat_loop(ws_mock)
    ws_mock.send.assert_called_once()
    sent_frame = json.loads(ws_mock.send.call_args[0][0])
    assert sent_frame["cmd"] == "ping"


@pytest.mark.asyncio
async def test_ws_session_loop(channel: WeComAiBotChannel, monkeypatch: pytest.MonkeyPatch) -> None:
    with patch("websockets.connect") as mock_connect:
        mock_ws = AsyncMock()
        mock_connect.return_value.__aenter__.return_value = mock_ws

        monkeypatch.setattr(channel, "_subscribe", AsyncMock(return_value=True))

        mock_ws.__aiter__.return_value = ['{"cmd": "pong"}', "invalid json"]

        await channel._ws_session()
        assert channel._active_streams == {}


@pytest.mark.asyncio
async def test_group_req_id_cache_on_msg_callback(channel: WeComAiBotChannel, monkeypatch: pytest.MonkeyPatch) -> None:
    """Group messages should cache req_id for proactive push fallback."""
    frame = {
        "headers": {"req_id": "group-req-123"},
        "body": {
            "msgid": "msg1",
            "chattype": "group",
            "chatid": "wrchat001",
            "from": {"userid": "user1"},
            "msgtype": "text",
            "text": {"content": "hello"},
        },
    }
    monkeypatch.setattr(channel, "_emit_inbound", AsyncMock())
    await channel._handle_msg_callback(frame)
    assert channel._group_req_ids["wrchat001"] == "group-req-123"


@pytest.mark.asyncio
async def test_group_req_id_cache_eviction(channel: WeComAiBotChannel, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cache should evict oldest entry when exceeding 500."""
    for i in range(501):
        channel._group_req_ids[f"wrchat{i:04d}"] = f"req-{i}"
    assert len(channel._group_req_ids) == 501
    frame = {
        "headers": {"req_id": "new-req"},
        "body": {
            "msgid": "msg-evict",
            "chattype": "group",
            "chatid": "wrchat_new",
            "from": {"userid": "user1"},
            "msgtype": "text",
            "text": {"content": "evict test"},
        },
    }
    monkeypatch.setattr(channel, "_emit_inbound", AsyncMock())
    await channel._handle_msg_callback(frame)
    assert len(channel._group_req_ids) == 501
    assert "wrchat0000" not in channel._group_req_ids
    assert "wrchat_new" in channel._group_req_ids


@pytest.mark.asyncio
async def test_proactive_msg_falls_back_to_respond_for_group(channel: WeComAiBotChannel, monkeypatch: pytest.MonkeyPatch) -> None:
    """Proactive push to group should use cached req_id via respond_msg."""
    channel._group_req_ids["wrchat001"] = "cached-req-abc"
    respond, send_frame = AsyncMock(), AsyncMock()
    monkeypatch.setattr(channel, "_send_respond_msg", respond)
    monkeypatch.setattr(channel, "_send_frame", send_frame)

    await channel._send_proactive_msg("wrchat001", "hello group")

    respond.assert_called_once_with("cached-req-abc", "hello group", finish=True)
    send_frame.assert_not_called()


@pytest.mark.asyncio
async def test_proactive_msg_dm_uses_send_msg(channel: WeComAiBotChannel, monkeypatch: pytest.MonkeyPatch) -> None:
    """DM proactive push should use aibot_send_msg directly."""
    send_frame = AsyncMock()
    monkeypatch.setattr(channel, "_send_frame", send_frame)

    await channel._send_proactive_msg("user123", "hello dm")

    send_frame.assert_called_once()
    frame = send_frame.call_args[0][0]
    assert frame["cmd"] == "aibot_send_msg"
    assert frame["body"]["chatid"] == "user123"


@pytest.mark.asyncio
async def test_edit_placeholder_force_closed_uses_state_req_id(
    channel: WeComAiBotChannel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Force-closed streams should use state.req_id directly, not proactive push."""
    from app.channels.providers.wecom.aibot_channel import WeComStreamState

    state = WeComStreamState(
        stream_id="stream1",
        chat_id="wrchat001",
        req_id="original-req-id",
    )
    state.is_force_closed = True
    channel._active_streams["stream1"] = state
    respond, proactive = AsyncMock(), AsyncMock()
    monkeypatch.setattr(channel, "_send_respond_msg", respond)
    monkeypatch.setattr(channel, "_send_proactive_msg", proactive)

    msg = OutboundMessage(channel="wecom_aibot", recipient_id="wrchat001", content="final result", user_id="u1")
    await channel.edit_placeholder_message("wrchat001", "stream1", msg)

    respond.assert_called_once_with("original-req-id", "final result", finish=True)
    proactive.assert_not_called()
