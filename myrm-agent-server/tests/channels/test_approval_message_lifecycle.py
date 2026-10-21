"""Tests for approval message lifecycle management.

Verifies that:
1. send_tracked() delivers messages and returns platform message_id
2. Approval commands edit the original prompt message
3. Fallback to new message when editing is unsupported
"""

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.bus import MessageBus
from app.channels.types import OutboundMessage


class FakeChannel(BaseChannel):
    """Channel that returns a message_id from send() and supports editing."""

    name = "test"

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[OutboundMessage] = []
        self.edits: list[tuple[str, str, str]] = []
        self._counter = 0

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)
        self._counter += 1
        return f"msg_{self._counter}"

    async def edit_message(self, chat_id: str, message_id: str, content: str) -> None:
        self.edits.append((chat_id, message_id, content))


class NoEditChannel(BaseChannel):
    """Channel that returns a message_id but does not support editing."""

    name = "noedit"

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[OutboundMessage] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)
        return "mid_1"

    async def edit_message(self, chat_id: str, message_id: str, content: str) -> None:
        raise NotImplementedError("This channel does not support editing")


class NoIdChannel(BaseChannel):
    """Channel that does not return a message_id."""

    name = "noid"

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[OutboundMessage] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)
        return None


@pytest.fixture
def bus() -> MessageBus:
    return MessageBus()


class TestSendTracked:
    @pytest.mark.asyncio
    async def test_returns_message_id(self, bus: MessageBus) -> None:
        ch = FakeChannel()
        bus.register_channel(ch)
        msg = OutboundMessage(channel="test", recipient_id="c1", content="hello", user_id="u1")
        mid = await bus.send_tracked(msg)
        assert mid == "msg_1"
        assert len(ch.sent) == 1

    @pytest.mark.asyncio
    async def test_returns_none_for_no_id_channel(self, bus: MessageBus) -> None:
        ch = NoIdChannel()
        bus.register_channel(ch)
        msg = OutboundMessage(channel="noid", recipient_id="c1", content="hello", user_id="u1")
        mid = await bus.send_tracked(msg)
        assert mid is None

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_channel(self, bus: MessageBus) -> None:
        msg = OutboundMessage(channel="unknown", recipient_id="c1", content="hello", user_id="u1")
        mid = await bus.send_tracked(msg)
        assert mid is None


class TestEditChannelMessage:
    @pytest.mark.asyncio
    async def test_edit_success(self, bus: MessageBus) -> None:
        ch = FakeChannel()
        bus.register_channel(ch)
        result = await bus.edit_channel_message("test", "c1", "msg_1", "Updated")
        assert result is True
        assert ch.edits == [("c1", "msg_1", "Updated")]

    @pytest.mark.asyncio
    async def test_edit_fails_gracefully(self, bus: MessageBus) -> None:
        ch = NoEditChannel()
        bus.register_channel(ch)
        result = await bus.edit_channel_message("noedit", "c1", "mid_1", "Updated")
        assert result is False

    @pytest.mark.asyncio
    async def test_edit_unknown_channel(self, bus: MessageBus) -> None:
        result = await bus.edit_channel_message("ghost", "c1", "m1", "Updated")
        assert result is False


class TestApprovalLifecycle:
    """Tests for message lifecycle during approval flow."""

    @pytest.mark.asyncio
    async def test_approve_edits_original_message(self, bus: MessageBus) -> None:
        ch = FakeChannel()
        bus.register_channel(ch)

        prompt = OutboundMessage(channel="test", recipient_id="c1", content="Approve bash_tool?", user_id="u1")
        mid = await bus.send_tracked(prompt)
        assert mid == "msg_1"

        edited = await bus.edit_channel_message("test", "c1", mid, " Approved: bash_tool")
        assert edited is True
        assert ch.edits[-1] == ("c1", "msg_1", " Approved: bash_tool")

    @pytest.mark.asyncio
    async def test_deny_edits_original_message(self, bus: MessageBus) -> None:
        ch = FakeChannel()
        bus.register_channel(ch)

        mid = await bus.send_tracked(OutboundMessage(channel="test", recipient_id="c1", content="Approve?", user_id="u1"))

        edited = await bus.edit_channel_message("test", "c1", mid, " Denied: bash_tool")
        assert edited is True
        assert "Denied" in ch.edits[-1][2]

    @pytest.mark.asyncio
    async def test_fallback_when_edit_unsupported(self, bus: MessageBus) -> None:
        ch = NoEditChannel()
        bus.register_channel(ch)

        mid = await bus.send_tracked(OutboundMessage(channel="noedit", recipient_id="c1", content="Approve?", user_id="u1"))
        assert mid == "mid_1"

        edited = await bus.edit_channel_message("noedit", "c1", mid, "Approved: bash_tool")
        assert edited is False

        fallback = OutboundMessage(channel="noedit", recipient_id="c1", content="Approved: bash_tool", user_id="u1")
        await bus.publish_outbound(fallback)

    @pytest.mark.asyncio
    async def test_fallback_when_no_message_id(self, bus: MessageBus) -> None:
        ch = NoIdChannel()
        bus.register_channel(ch)

        mid = await bus.send_tracked(OutboundMessage(channel="noid", recipient_id="c1", content="Approve?", user_id="u1"))
        assert mid is None
