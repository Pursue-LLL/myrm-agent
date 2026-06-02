"""WeComAiBotChannel tests — contract, lifecycle, inbound, outbound, streaming, diagnostics."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.channels.core.base import BaseChannel
from app.channels.providers.wecom.aibot_channel import (
    WeComAiBotChannel,
    WeComStreamState,
)
from app.channels.types import (
    ChannelStatus,
    InboundMessage,
    OutboundMessage,
)
from app.channels.types.status import IssueKind, IssueSeverity

from .channel_test_base import ChannelTestBase

# ── Contract ──────────────────────────────────────────────────


class TestWeComAiBotContract(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return WeComAiBotChannel(bot_id="test_bot", secret="test_secret")


# ── Helpers ───────────────────────────────────────────────────


def _make_channel(bot_id: str = "bot123", secret: str = "sec456") -> WeComAiBotChannel:
    return WeComAiBotChannel(bot_id=bot_id, secret=secret)


def _msg_callback_frame(
    content: str = "hello",
    msg_type: str = "text",
    req_id: str = "req_001",
    msg_id: str = "m1",
    chat_type: str = "single",
    chat_id: str = "chat_001",
    sender_id: str = "user_001",
) -> dict[str, object]:
    body: dict[str, object] = {
        "msgid": msg_id,
        "chattype": chat_type,
        "chatid": chat_id,
        "from": {"userid": sender_id},
        "msgtype": msg_type,
    }
    if msg_type == "text":
        body["text"] = {"content": content}
    elif msg_type == "image":
        body["image"] = {"url": "https://img.example.com/1.jpg"}
    elif msg_type == "file":
        body["file"] = {"filename": "doc.pdf"}
    elif msg_type == "location":
        body["location"] = {"latitude": "39.9", "longitude": "116.4", "label": "Beijing"}
    elif msg_type == "link":
        body["link"] = {"title": "Example", "url": "https://example.com"}
    return {
        "cmd": "aibot_msg_callback",
        "headers": {"req_id": req_id},
        "body": body,
    }


def _event_callback_frame(
    event_type: str = "enter_chat",
    req_id: str = "req_002",
    sender_id: str = "user_001",
) -> dict[str, object]:
    return {
        "cmd": "aibot_event_callback",
        "headers": {"req_id": req_id},
        "body": {
            "from": {"userid": sender_id},
            "event": {"eventtype": event_type},
            "msgid": "ev_m1",
        },
    }


# ── Lifecycle ─────────────────────────────────────────────────


class TestLifecycle:
    def test_initial_state(self) -> None:
        ch = _make_channel()
        assert ch.status == ChannelStatus.IDLE
        assert ch._ws is None
        assert ch._ws_task is None

    @pytest.mark.asyncio
    async def test_start_without_credentials_stays_idle(self) -> None:
        ch = WeComAiBotChannel(bot_id="", secret="")
        await ch.start()
        assert ch.status == ChannelStatus.IDLE
        assert ch._ws_task is None

    @pytest.mark.asyncio
    async def test_stop_from_idle(self) -> None:
        ch = _make_channel()
        await ch.stop()
        assert ch.status == ChannelStatus.STOPPED
        assert ch._ws is None

    @pytest.mark.asyncio
    async def test_health_check_idle(self) -> None:
        ch = _make_channel()
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_running_no_ws(self) -> None:
        ch = _make_channel()
        ch._WeComAiBotChannel__status = ChannelStatus.RUNNING  # type: ignore[attr-defined]
        ch._status = ChannelStatus.RUNNING
        assert await ch.health_check() is False


# ── Diagnostics ───────────────────────────────────────────────


class TestDiagnostics:
    def test_no_issues_when_configured(self) -> None:
        ch = _make_channel()
        issues = ch.collect_issues()
        assert len(issues) == 0

    def test_missing_bot_id(self) -> None:
        ch = WeComAiBotChannel(bot_id="", secret="sec")
        issues = ch.collect_issues()
        assert any(i.kind == IssueKind.CONFIG and "Bot ID" in i.message for i in issues)

    def test_missing_secret(self) -> None:
        ch = WeComAiBotChannel(bot_id="bot", secret="")
        issues = ch.collect_issues()
        assert any(i.kind == IssueKind.CONFIG and "Secret" in i.message for i in issues)

    def test_error_state_issue(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.ERROR
        issues = ch.collect_issues()
        assert any(i.kind == IssueKind.RUNTIME and i.severity == IssueSeverity.ERROR for i in issues)

    def test_last_error_issue(self) -> None:
        ch = _make_channel()
        ch.health.record_failure("connection reset")
        issues = ch.collect_issues()
        assert any("connection reset" in i.message for i in issues)


# ── Inbound: Message Callback ─────────────────────────────────


class TestInboundMessageCallback:
    @pytest.mark.asyncio
    async def test_text_message(self) -> None:
        ch = _make_channel()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(AsyncMock(side_effect=lambda m: received.append(m)))

        frame = _msg_callback_frame(content="hello world")
        await ch._handle_msg_callback(frame)

        assert len(received) == 1
        msg = received[0]
        assert msg.content == "hello world"
        assert msg.sender_id == "user_001"
        assert msg.channel == "wecom_aibot"
        assert msg.mentioned is True
        assert msg.message_id == "m1"
        assert msg.thread_id == "req_001"
        assert msg.metadata.get("req_id") == "req_001"

    @pytest.mark.asyncio
    async def test_group_message(self) -> None:
        ch = _make_channel()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(AsyncMock(side_effect=lambda m: received.append(m)))

        frame = _msg_callback_frame(chat_type="group", chat_id="group_001")
        await ch._handle_msg_callback(frame)

        assert len(received) == 1
        msg = received[0]
        assert msg.is_group is True
        assert msg.chat_id == "group_001"
        assert msg.mentioned is True

    @pytest.mark.asyncio
    async def test_dm_uses_sender_as_chat_id(self) -> None:
        ch = _make_channel()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(AsyncMock(side_effect=lambda m: received.append(m)))

        frame = _msg_callback_frame(chat_type="single", sender_id="user_x")
        await ch._handle_msg_callback(frame)

        assert received[0].chat_id == "user_x"
        assert received[0].is_group is False

    @pytest.mark.asyncio
    async def test_image_message(self) -> None:
        ch = _make_channel()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(AsyncMock(side_effect=lambda m: received.append(m)))

        frame = _msg_callback_frame(msg_type="image")
        await ch._handle_msg_callback(frame)

        assert len(received) == 1
        assert len(received[0].media) == 1
        assert received[0].media[0].url == "https://img.example.com/1.jpg"

    @pytest.mark.asyncio
    async def test_file_message(self) -> None:
        ch = _make_channel()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(AsyncMock(side_effect=lambda m: received.append(m)))

        frame = _msg_callback_frame(msg_type="file")
        await ch._handle_msg_callback(frame)

        assert len(received) == 1
        assert received[0].media[0].filename == "doc.pdf"

    @pytest.mark.asyncio
    async def test_location_message(self) -> None:
        ch = _make_channel()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(AsyncMock(side_effect=lambda m: received.append(m)))

        frame = _msg_callback_frame(msg_type="location")
        await ch._handle_msg_callback(frame)

        assert len(received) == 1
        assert "Beijing" in received[0].content
        assert "39.9" in received[0].content

    @pytest.mark.asyncio
    async def test_link_message(self) -> None:
        ch = _make_channel()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(AsyncMock(side_effect=lambda m: received.append(m)))

        frame = _msg_callback_frame(msg_type="link")
        await ch._handle_msg_callback(frame)

        assert len(received) == 1
        assert "Example" in received[0].content
        assert "https://example.com" in received[0].content

    @pytest.mark.asyncio
    async def test_empty_content_ignored(self) -> None:
        ch = _make_channel()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(AsyncMock(side_effect=lambda m: received.append(m)))

        frame = _msg_callback_frame(content="", msg_type="text")
        await ch._handle_msg_callback(frame)

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_invalid_frame_ignored(self) -> None:
        ch = _make_channel()
        ch.set_inbound_handler(AsyncMock())
        await ch._handle_msg_callback({"headers": "not_a_dict", "body": {}})
        assert ch._inbound_handler.call_count == 0  # type: ignore[union-attr]


# ── Inbound: Event Callback ──────────────────────────────────


class TestInboundEventCallback:
    @pytest.mark.asyncio
    async def test_enter_chat_event(self) -> None:
        ch = _make_channel()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(AsyncMock(side_effect=lambda m: received.append(m)))

        frame = _event_callback_frame(event_type="enter_chat", sender_id="new_user")
        await ch._handle_event_callback(frame)

        assert len(received) == 1
        msg = received[0]
        assert msg.content == ""
        assert msg.sender_id == "new_user"
        assert msg.chat_id == "new_user"
        assert msg.metadata.get("event_type") == "enter_chat"
        assert msg.thread_id == "req_002"

    @pytest.mark.asyncio
    async def test_unknown_event_ignored(self) -> None:
        ch = _make_channel()
        ch.set_inbound_handler(AsyncMock())

        frame = _event_callback_frame(event_type="unknown_event")
        await ch._handle_event_callback(frame)

        assert ch._inbound_handler.call_count == 0  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_enter_chat_without_sender_ignored(self) -> None:
        ch = _make_channel()
        ch.set_inbound_handler(AsyncMock())

        frame = _event_callback_frame(sender_id="")
        await ch._handle_event_callback(frame)

        assert ch._inbound_handler.call_count == 0  # type: ignore[union-attr]


# ── Outbound: send ────────────────────────────────────────────


class TestOutboundSend:
    @pytest.mark.asyncio
    async def test_send_without_ws_returns_none(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(
            channel="wecom_aibot",
            recipient_id="chat1",
            content="hi",
            user_id="u1",
        )
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_with_req_id_uses_stream(self) -> None:
        ch = _make_channel()
        mock_ws = AsyncMock()
        ch._ws = mock_ws

        msg = OutboundMessage(
            channel="wecom_aibot",
            recipient_id="chat1",
            content="response text",
            user_id="u1",
            metadata={"req_id": "req_abc"},
        )
        await ch.send(msg)

        assert mock_ws.send.called
        sent_data = json.loads(mock_ws.send.call_args_list[-1][0][0])
        assert sent_data["cmd"] == "aibot_respond_msg"
        assert sent_data["body"]["stream"]["finish"] is True
        assert "response text" in sent_data["body"]["stream"]["content"]

    @pytest.mark.asyncio
    async def test_send_without_req_id_uses_proactive(self) -> None:
        ch = _make_channel()
        mock_ws = AsyncMock()
        ch._ws = mock_ws

        msg = OutboundMessage(
            channel="wecom_aibot",
            recipient_id="chat1",
            content="proactive msg",
            user_id="u1",
        )
        await ch.send(msg)

        assert mock_ws.send.called
        sent_data = json.loads(mock_ws.send.call_args_list[-1][0][0])
        assert sent_data["cmd"] == "aibot_send_msg"
        assert sent_data["body"]["chatid"] == "chat1"

    @pytest.mark.asyncio
    async def test_send_without_recipient_and_req_id_warns(self) -> None:
        ch = _make_channel()
        mock_ws = AsyncMock()
        ch._ws = mock_ws

        msg = OutboundMessage(
            channel="wecom_aibot",
            recipient_id="",
            content="orphan msg",
            user_id="u1",
        )
        result = await ch.send(msg)
        assert result is None
        assert not mock_ws.send.called


# ── Outbound: Placeholder / Streaming ─────────────────────────


class TestPlaceholderStreaming:
    @pytest.mark.asyncio
    async def test_send_placeholder_returns_stream_id(self) -> None:
        ch = _make_channel()
        mock_ws = AsyncMock()
        ch._ws = mock_ws

        stream_id = await ch.send_placeholder("chat1", "Thinking...", thread_id="req_xyz")

        assert stream_id is not None
        assert len(stream_id) == 16
        assert stream_id in ch._active_streams
        assert ch._active_streams[stream_id].req_id == "req_xyz"

        sent_data = json.loads(mock_ws.send.call_args[0][0])
        assert sent_data["body"]["stream"]["finish"] is False

    @pytest.mark.asyncio
    async def test_send_placeholder_without_thread_id_returns_none(self) -> None:
        ch = _make_channel()
        ch._ws = AsyncMock()

        result = await ch.send_placeholder("chat1", "text")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_placeholder_without_ws_returns_none(self) -> None:
        ch = _make_channel()
        result = await ch.send_placeholder("chat1", "text", thread_id="req_1")
        assert result is None

    @pytest.mark.asyncio
    async def test_edit_message_updates_stream(self) -> None:
        ch = _make_channel()
        mock_ws = AsyncMock()
        ch._ws = mock_ws
        ch._active_streams["sid_1"] = WeComStreamState(stream_id="sid_1", chat_id="chat1", req_id="req_1")

        await ch.edit_message("chat1", "sid_1", "Searching...")

        sent_data = json.loads(mock_ws.send.call_args[0][0])
        assert sent_data["body"]["stream"]["finish"] is False
        assert sent_data["body"]["stream"]["content"] == "Searching..."
        assert sent_data["body"]["stream"]["id"] == "sid_1"

    @pytest.mark.asyncio
    async def test_edit_message_unknown_stream_noop(self) -> None:
        ch = _make_channel()
        ch._ws = AsyncMock()

        await ch.edit_message("chat1", "unknown_sid", "text")
        assert not ch._ws.send.called

    @pytest.mark.asyncio
    async def test_edit_placeholder_message_finalizes(self) -> None:
        ch = _make_channel()
        mock_ws = AsyncMock()
        ch._ws = mock_ws
        ch._active_streams["sid_2"] = WeComStreamState(stream_id="sid_2", chat_id="chat1", req_id="req_2")

        msg = OutboundMessage(
            channel="wecom_aibot",
            recipient_id="chat1",
            content="Final answer",
            user_id="u1",
        )
        await ch.edit_placeholder_message("chat1", "sid_2", msg)

        sent_data = json.loads(mock_ws.send.call_args[0][0])
        assert sent_data["body"]["stream"]["finish"] is True
        assert "Final answer" in sent_data["body"]["stream"]["content"]
        assert "sid_2" not in ch._active_streams


# ── Frame Dispatch ────────────────────────────────────────────


class TestFrameDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_msg_callback(self) -> None:
        ch = _make_channel()
        ch.set_inbound_handler(AsyncMock())

        frame = _msg_callback_frame()
        await ch._handle_frame(frame)

        assert ch._inbound_handler.call_count == 1  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_dispatch_event_callback(self) -> None:
        ch = _make_channel()
        ch.set_inbound_handler(AsyncMock())

        frame = _event_callback_frame()
        await ch._handle_frame(frame)

        assert ch._inbound_handler.call_count == 1  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_dispatch_pong_noop(self) -> None:
        ch = _make_channel()
        await ch._handle_frame({"cmd": "pong"})

    @pytest.mark.asyncio
    async def test_dispatch_unknown_cmd(self) -> None:
        ch = _make_channel()
        await ch._handle_frame({"cmd": "unknown_xyz"})


# ── Subscribe ─────────────────────────────────────────────────


class TestSubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_success(self) -> None:
        ch = _make_channel()
        mock_ws = AsyncMock()
        mock_ws.recv.return_value = json.dumps(
            {
                "cmd": "aibot_subscribe",
                "body": {"ret_code": 0, "ret_msg": "ok"},
            }
        )

        result = await ch._subscribe(mock_ws)
        assert result is True

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["cmd"] == "aibot_subscribe"
        assert sent["body"]["bot_id"] == "bot123"
        assert sent["body"]["secret"] == "sec456"

    @pytest.mark.asyncio
    async def test_subscribe_failure(self) -> None:
        ch = _make_channel()
        mock_ws = AsyncMock()
        mock_ws.recv.return_value = json.dumps(
            {
                "body": {"ret_code": 40001, "ret_msg": "invalid secret"},
            }
        )

        result = await ch._subscribe(mock_ws)
        assert result is False

    @pytest.mark.asyncio
    async def test_subscribe_timeout(self) -> None:
        ch = _make_channel()
        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = TimeoutError()

        result = await ch._subscribe(mock_ws)
        assert result is False


# ── Send Frame Helpers ────────────────────────────────────────


class TestSendFrameHelpers:
    @pytest.mark.asyncio
    async def test_send_frame_without_ws_noop(self) -> None:
        ch = _make_channel()
        await ch._send_frame({"cmd": "test"})

    @pytest.mark.asyncio
    async def test_send_frame_error_records_failure(self) -> None:
        ch = _make_channel()
        mock_ws = AsyncMock()
        mock_ws.send.side_effect = ConnectionError("broken pipe")
        ch._ws = mock_ws

        await ch._send_frame({"cmd": "test"})
        assert ch.health.last_error == "broken pipe"

    @pytest.mark.asyncio
    async def test_send_respond_msg_format(self) -> None:
        ch = _make_channel()
        mock_ws = AsyncMock()
        ch._ws = mock_ws

        await ch._send_respond_msg("req_1", "hello", finish=False, stream_id="s1")

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["cmd"] == "aibot_respond_msg"
        assert sent["headers"]["req_id"] == "req_1"
        assert sent["body"]["stream"]["id"] == "s1"
        assert sent["body"]["stream"]["finish"] is False
        assert sent["body"]["stream"]["content"] == "hello"

    @pytest.mark.asyncio
    async def test_send_proactive_msg_format(self) -> None:
        ch = _make_channel()
        mock_ws = AsyncMock()
        ch._ws = mock_ws

        await ch._send_proactive_msg("chat_1", "proactive hello")

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["cmd"] == "aibot_send_msg"
        assert sent["body"]["chatid"] == "chat_1"
        assert sent["body"]["text"]["content"] == "proactive hello"


# ── Pending Streams Cleanup ───────────────────────────────────


class TestActiveStreamsCleanup:
    @pytest.mark.asyncio
    async def test_stop_clears_active_streams(self) -> None:
        ch = _make_channel()
        ch._active_streams["s1"] = WeComStreamState(stream_id="s1", chat_id="c1", req_id="r1")
        ch._active_streams["s2"] = WeComStreamState(stream_id="s2", chat_id="c1", req_id="r2")

        await ch.stop()
        assert len(ch._active_streams) == 0

    @pytest.mark.asyncio
    async def test_edit_placeholder_pops_stream(self) -> None:
        ch = _make_channel()
        ch._ws = AsyncMock()
        ch._active_streams["s1"] = WeComStreamState(stream_id="s1", chat_id="c1", req_id="r1")

        msg = OutboundMessage(
            channel="wecom_aibot",
            recipient_id="c1",
            content="done",
            user_id="u1",
        )
        await ch.edit_placeholder_message("c1", "s1", msg)

        assert "s1" not in ch._active_streams


# ── Parse Message Content ─────────────────────────────────────


class TestParseMessageContent:
    def test_parse_text(self) -> None:
        ch = _make_channel()
        content, media = ch._parse_msg_content({"msgtype": "text", "text": {"content": "  hi  "}})
        assert content == "hi"
        assert media == []

    def test_parse_voice(self) -> None:
        ch = _make_channel()
        content, media = ch._parse_msg_content({"msgtype": "voice"})
        assert content == ""
        assert len(media) == 1

    def test_parse_video(self) -> None:
        ch = _make_channel()
        content, media = ch._parse_msg_content({"msgtype": "video"})
        assert content == ""
        assert len(media) == 1

    def test_parse_unknown_type(self) -> None:
        ch = _make_channel()
        content, media = ch._parse_msg_content({"msgtype": "sticker"})
        assert content == ""
        assert media == []
