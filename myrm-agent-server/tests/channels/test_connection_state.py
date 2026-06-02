"""Tests for BaseChannel connection state management and Gateway event integration.

Covers:
- BaseChannel._set_connected deduplication
- BaseChannel.is_connected property
- connection_change event emission
- start/stop lifecycle connection state
- Gateway remove_channel clears listeners
- WhatsApp post-connect groups scheduling
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.gateway import ChannelGateway
from app.channels.types import (
    ChannelCapabilities,
    ChannelStatus,
    OutboundMessage,
)


class StubChannel(BaseChannel):
    name = "stub"
    capabilities = ChannelCapabilities()

    def __init__(self, *, channel_name: str = "stub") -> None:
        super().__init__()
        type(self).name = channel_name  # type: ignore[assignment]
        self.sent: list[OutboundMessage] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)
        return "msg_ok"


def _make_stub(name: str = "stub") -> StubChannel:
    return StubChannel(channel_name=name)


def _make_instance(channel_type: str, instance_id: str) -> StubChannel:
    ch = _make_stub(f"{channel_type}_{instance_id}")
    ch.channel_type = channel_type
    return ch


# ── BaseChannel._set_connected ──────────────────────────────────


class TestSetConnected:
    def test_initial_state_disconnected(self) -> None:
        ch = _make_stub()
        assert ch.is_connected is False

    def test_set_connected_true(self) -> None:
        ch = _make_stub()
        ch._set_connected(True)
        assert ch.is_connected is True

    def test_set_connected_false(self) -> None:
        ch = _make_stub()
        ch._set_connected(True)
        ch._set_connected(False)
        assert ch.is_connected is False

    def test_dedup_same_state_no_event(self) -> None:
        """Calling _set_connected with same value should NOT emit."""
        ch = _make_stub()
        events: list[dict[str, Any]] = []
        ch.on("connection_change", lambda _name, data: events.append(data))

        ch._set_connected(False)
        assert len(events) == 0

    def test_dedup_true_to_true_no_event(self) -> None:
        ch = _make_stub()
        ch._set_connected(True)
        events: list[dict[str, Any]] = []
        ch.on("connection_change", lambda _name, data: events.append(data))

        ch._set_connected(True)
        assert len(events) == 0

    def test_transition_emits_event(self) -> None:
        ch = _make_stub()
        events: list[dict[str, Any]] = []
        ch.on("connection_change", lambda _name, data: events.append(data))

        ch._set_connected(True)
        assert len(events) == 1
        assert events[0] == {"connected": True}

        ch._set_connected(False)
        assert len(events) == 2
        assert events[1] == {"connected": False}

    def test_rapid_toggle(self) -> None:
        ch = _make_stub()
        events: list[dict[str, Any]] = []
        ch.on("connection_change", lambda _name, data: events.append(data))

        for _ in range(5):
            ch._set_connected(True)
            ch._set_connected(False)

        assert len(events) == 10
        assert all(e["connected"] is True for e in events[::2])
        assert all(e["connected"] is False for e in events[1::2])


# ── BaseChannel start/stop lifecycle ─────────────────────────────


class TestLifecycleConnection:
    @pytest.mark.asyncio
    async def test_start_sets_connected(self) -> None:
        ch = _make_stub()
        await ch.start()
        assert ch.is_connected is True
        assert ch.status == ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_stop_clears_connected(self) -> None:
        ch = _make_stub()
        await ch.start()
        await ch.stop()
        assert ch.is_connected is False
        assert ch.status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_start_emits_connected_event(self) -> None:
        ch = _make_stub()
        events: list[dict[str, Any]] = []
        ch.on("connection_change", lambda _name, data: events.append(data))

        await ch.start()
        assert len(events) == 1
        assert events[0]["connected"] is True

    @pytest.mark.asyncio
    async def test_stop_emits_disconnected_event(self) -> None:
        ch = _make_stub()
        await ch.start()
        events: list[dict[str, Any]] = []
        ch.on("connection_change", lambda _name, data: events.append(data))

        await ch.stop()
        assert len(events) == 1
        assert events[0]["connected"] is False

    @pytest.mark.asyncio
    async def test_double_stop_no_duplicate_event(self) -> None:
        ch = _make_stub()
        await ch.start()
        events: list[dict[str, Any]] = []
        ch.on("connection_change", lambda _name, data: events.append(data))

        await ch.stop()
        await ch.stop()
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_stop_from_idle_emits_nothing(self) -> None:
        """Stopping a never-started channel should not emit (already disconnected)."""
        ch = _make_stub()
        events: list[dict[str, Any]] = []
        ch.on("connection_change", lambda _name, data: events.append(data))

        await ch.stop()
        assert len(events) == 0


# ── Gateway remove_channel clears listeners ──────────────────────


class TestRemoveChannelClearsListeners:
    @pytest.mark.asyncio
    async def test_remove_clears_all_listeners(self) -> None:
        """After remove_channel, previously registered listeners should be gone."""
        gw = ChannelGateway()
        ch = _make_stub("test_ch")
        gw.register(ch)
        await gw.start()
        try:
            pre_remove_calls: list[str] = []
            ch.on("custom_evt", lambda _n, _d: pre_remove_calls.append("custom"))

            await gw.remove_channel("test_ch")

            ch.emit("custom_evt")
            assert pre_remove_calls == [], "Listener registered before remove should be cleared"
        finally:
            await gw.stop()

    @pytest.mark.asyncio
    async def test_remove_instance_clears_listeners(self) -> None:
        gw = ChannelGateway()
        gw.register(_make_stub("wechat"))
        await gw.start()
        try:
            inst = _make_instance("wechat", "rm_test")
            await gw.add_channel(inst)

            listener_calls: list[str] = []
            inst.on("connection_change", lambda _n, _d: listener_calls.append("conn"))

            await gw.remove_channel("wechat_rm_test")

            inst.emit("connection_change", {"connected": True})
            assert listener_calls == []
        finally:
            await gw.stop()


# ── Gateway connection_change event forwarding ───────────────────


class TestGatewayConnectionEvent:
    @pytest.mark.asyncio
    async def test_gateway_receives_connection_change(self) -> None:
        gw = ChannelGateway()
        ch = _make_stub("evt_ch")
        gw.register(ch)

        received: list[tuple[str, bool]] = []

        def on_conn(name: str, connected: bool) -> None:
            received.append((name, connected))

        gw.set_connection_change_callback(on_conn)
        await gw.start()
        try:
            await asyncio.sleep(0.05)
            assert any(c is True for _, c in received)
        finally:
            await gw.stop()

    @pytest.mark.asyncio
    async def test_gateway_receives_disconnect_on_stop(self) -> None:
        gw = ChannelGateway()
        ch = _make_stub("stop_ch")
        gw.register(ch)

        received: list[tuple[str, bool]] = []

        def on_conn(name: str, connected: bool) -> None:
            received.append((name, connected))

        gw.set_connection_change_callback(on_conn)
        await gw.start()
        await asyncio.sleep(0.05)
        received.clear()

        await gw.stop()
        disconnect_events = [(n, c) for n, c in received if c is False]
        assert len(disconnect_events) >= 1


# ── WhatsApp post-connect groups ─────────────────────────────────


class TestWhatsAppPostConnect:
    @pytest.mark.asyncio
    async def test_post_connect_groups_scheduled(self) -> None:
        """After WhatsApp connects, _post_connect_groups should be scheduled."""
        from app.channels.providers.whatsapp.channel import (
            WhatsAppChannel,
        )

        ch = WhatsAppChannel(auth_dir="/tmp/test_wa_post_connect")
        ch._process = MagicMock()
        ch._process.stdin = MagicMock()
        ch._process.stdin.write = MagicMock()
        ch._process.stdin.drain = AsyncMock()
        ch._process.returncode = None

        with patch.object(ch, "list_groups", new_callable=AsyncMock, return_value=[]) as mock_lg:
            ch._handle_connection_event({"status": "open", "jid": "123@s.whatsapp.net"})
            assert ch.is_connected is True

            await asyncio.sleep(4)
            mock_lg.assert_called_once_with(force_refresh=True)


# ── status_change event ──────────────────────────────────────────


# ── BaseChannel inbound pipeline ──────────────────────────────────


class TestInboundPipeline:
    @pytest.mark.asyncio
    async def test_emit_inbound_dispatches_to_handler(self) -> None:
        ch = _make_stub()
        await ch.start()
        received: list[Any] = []

        async def handler(msg: Any) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)
        from app.channels.types import InboundMessage

        msg = InboundMessage(channel="stub", sender_id="user1", content="hello", chat_id="chat1")
        await ch._emit_inbound(msg)
        assert len(received) == 1
        assert received[0].content == "hello"

    @pytest.mark.asyncio
    async def test_emit_inbound_filters_bot_self(self) -> None:
        ch = _make_stub()
        await ch.start()
        ch._bot_id = "bot123"
        received: list[Any] = []

        async def handler(msg: Any) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)
        from app.channels.types import InboundMessage

        msg = InboundMessage(channel="stub", sender_id="bot123", content="self", chat_id="chat1")
        await ch._emit_inbound(msg)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_emit_inbound_dedup(self) -> None:
        ch = _make_stub()
        await ch.start()
        received: list[Any] = []

        async def handler(msg: Any) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)
        from app.channels.types import InboundMessage

        msg = InboundMessage(channel="stub", sender_id="user1", content="hello", chat_id="chat1", message_id="dup1")
        await ch._emit_inbound(msg)
        await ch._emit_inbound(msg)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_emit_inbound_disabled_channel_drops(self) -> None:
        ch = _make_stub()
        ch._status = ChannelStatus.DISABLED
        received: list[Any] = []

        async def handler(msg: Any) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)
        from app.channels.types import InboundMessage

        msg = InboundMessage(channel="stub", sender_id="user1", content="hello", chat_id="chat1")
        await ch._emit_inbound(msg)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_dispatch_inbound_no_handler_logs_warning(self) -> None:
        ch = _make_stub()
        from app.channels.types import InboundMessage

        msg = InboundMessage(channel="stub", sender_id="user1", content="hello", chat_id="chat1")
        await ch._dispatch_inbound(msg)

    @pytest.mark.asyncio
    async def test_debounce_emit(self) -> None:
        ch = _make_stub()
        ch._debounce_seconds = 0.1
        await ch.start()
        received: list[Any] = []

        async def handler(msg: Any) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)
        from app.channels.types import InboundMessage

        msg1 = InboundMessage(channel="stub", sender_id="user1", content="first", chat_id="chat1")
        msg2 = InboundMessage(channel="stub", sender_id="user1", content="second", chat_id="chat1")
        await ch._emit_inbound(msg1)
        await ch._emit_inbound(msg2)
        await asyncio.sleep(0.3)
        assert len(received) == 1
        assert received[0].content == "second"

    def test_evict_expired_dedup(self) -> None:
        from app.channels.core.base import DedupMode

        ch = _make_stub()
        ch._dedup_mode = DedupMode.TTL
        ch._dedup_ttl = 1.0
        import time

        now = time.monotonic()
        ch._seen_msg_ids["old"] = now - 2.0
        ch._seen_msg_ids["new"] = now
        ch._evict_expired_dedup(now)
        assert "old" not in ch._seen_msg_ids
        assert "new" in ch._seen_msg_ids


# ── BaseChannel misc methods ─────────────────────────────────────


class TestBaseChannelMisc:
    @pytest.mark.asyncio
    async def test_send_placeholder_returns_none(self) -> None:
        ch = _make_stub()
        result = await ch.send_placeholder("chat1", "loading...")
        assert result is None

    @pytest.mark.asyncio
    async def test_create_thread_returns_none(self) -> None:
        ch = _make_stub()
        result = await ch.create_thread("chat1", "thread_name")
        assert result is None

    @pytest.mark.asyncio
    async def test_health_check_default(self) -> None:
        ch = _make_stub()
        assert await ch.health_check() is False
        await ch.start()
        assert await ch.health_check() is True

    def test_collect_issues_empty(self) -> None:
        ch = _make_stub()
        assert ch.collect_issues() == []

    def test_collect_issues_with_error(self) -> None:
        ch = _make_stub()
        ch.health.last_error = "connection refused"
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert "connection refused" in issues[0].message

    @pytest.mark.asyncio
    async def test_edit_placeholder_message_fallback(self) -> None:
        ch = _make_stub()
        edited: list[tuple[str, str, str]] = []

        async def mock_edit(chat_id: str, msg_id: str, text: str) -> None:
            edited.append((chat_id, msg_id, text))

        ch.edit_message = mock_edit  # type: ignore[assignment]
        msg = OutboundMessage(channel="stub", recipient_id="chat1", content="final", user_id="test")
        await ch.edit_placeholder_message("chat1", "msg1", msg)
        assert edited == [("chat1", "msg1", "final")]

    def test_build_inbound(self) -> None:
        ch = _make_stub("test_build")
        msg = ch._build_inbound("sender1", "hello", "chat1")
        assert msg.channel == "test_build"
        assert msg.sender_id == "sender1"
        assert msg.content == "hello"

    def test_should_retry_default(self) -> None:
        ch = _make_stub()
        assert ch.should_retry(ConnectionError("test")) is True

    def test_extract_retry_after_default(self) -> None:
        ch = _make_stub()
        result = ch.extract_retry_after(ValueError("test"))
        assert result is None


# ── status_change event ──────────────────────────────────────────


class TestStatusChangeEvent:
    @pytest.mark.asyncio
    async def test_status_change_emitted_on_start(self) -> None:
        ch = _make_stub()
        events: list[dict[str, Any]] = []
        ch.on("status_change", lambda _name, data: events.append(data))

        await ch.start()
        assert len(events) >= 1
        assert events[0]["new_status"] == ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_status_change_emitted_on_stop(self) -> None:
        ch = _make_stub()
        await ch.start()
        events: list[dict[str, Any]] = []
        ch.on("status_change", lambda _name, data: events.append(data))

        await ch.stop()
        assert len(events) >= 1
        assert events[-1]["new_status"] == ChannelStatus.STOPPED

    def test_no_event_on_same_status(self) -> None:
        ch = _make_stub()
        ch._status = ChannelStatus.IDLE
        events: list[dict[str, Any]] = []
        ch.on("status_change", lambda _name, data: events.append(data))

        ch._status = ChannelStatus.IDLE
        assert len(events) == 0
