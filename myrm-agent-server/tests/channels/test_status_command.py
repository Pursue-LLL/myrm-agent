"""Tests for /status command handler."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.protocols.status import (
    SessionStatus,
    StatusProvider,
)
from app.channels.routing.command_defs import (
    SYSTEM_COMMANDS,
    CommandAction,
)
from app.channels.routing.router_commands import (
    RouterCommandsMixin,
)
from app.channels.types import InboundMessage


@pytest.fixture
def inbound_msg() -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user123",
        chat_id="user123",
        content="/status",
        is_group=False,
    )


class TestStatusCommandDef:
    """Verify /status is registered in SYSTEM_COMMANDS."""

    def test_status_action_exists(self) -> None:
        assert hasattr(CommandAction, "STATUS")
        assert CommandAction.STATUS.value == "status"

    def test_status_in_system_commands(self) -> None:
        names = [c.name for c in SYSTEM_COMMANDS]
        assert "status" in names

    def test_status_command_category(self) -> None:
        cmd = next(c for c in SYSTEM_COMMANDS if c.name == "status")
        assert cmd.category == "Info"
        assert cmd.parse_args is False


class TestStatusProviderProtocol:
    """Verify StatusProvider protocol compliance."""

    def test_protocol_is_runtime_checkable(self) -> None:
        class MockProvider:
            async def get_session_status(
                self, channel: str, peer_id: str
            ) -> SessionStatus | None:
                return None

        assert isinstance(MockProvider(), StatusProvider)

    def test_session_status_frozen(self) -> None:
        status = SessionStatus(session_id="abc123", title="Test", total_tokens=1000)
        with pytest.raises(FrozenInstanceError):
            status.session_id = "new"  # type: ignore[misc]


class TestHandleStatusCommand:
    """Integration test for _handle_status_command via router mixin."""

    @staticmethod
    def _make_host(
        *,
        status_provider: object = None,
        active_tasks: dict | None = None,
        session_yolo: dict | None = None,
    ) -> MagicMock:
        mock_bus = MagicMock()
        mock_bus.publish_outbound = AsyncMock()

        mock_gate = MagicMock()
        mock_gate.pending_count = MagicMock(return_value=0)

        host = MagicMock()
        host._status_provider = status_provider
        host._active_tasks = active_tasks or {}
        host._session_yolo = session_yolo or {}
        host._bus = mock_bus
        host._gate = mock_gate
        return host

    @pytest.mark.asyncio
    async def test_status_with_provider(self, inbound_msg: InboundMessage) -> None:
        mock_provider = AsyncMock()
        mock_provider.get_session_status.return_value = SessionStatus(
            session_id="chat_abc123def456",
            title="Research on AI",
            total_tokens=15000,
            model_name="claude-4-sonnet",
        )

        host = self._make_host(status_provider=mock_provider)
        await RouterCommandsMixin._handle_status_command(host, inbound_msg)

        host._bus.publish_outbound.assert_called_once()
        reply = host._bus.publish_outbound.call_args[0][0]
        assert "chat_abc123d" in reply.content
        assert "Research on AI" in reply.content
        assert "claude-4-sonnet" in reply.content
        assert "15,000" in reply.content
        assert "Idle" in reply.content

    @pytest.mark.asyncio
    async def test_status_without_provider(self, inbound_msg: InboundMessage) -> None:
        host = self._make_host(status_provider=None)
        await RouterCommandsMixin._handle_status_command(host, inbound_msg)

        host._bus.publish_outbound.assert_called_once()
        reply = host._bus.publish_outbound.call_args[0][0]
        assert "Idle" in reply.content

    @pytest.mark.asyncio
    async def test_status_shows_running_agent(self, inbound_msg: InboundMessage) -> None:
        mock_provider = AsyncMock()
        mock_provider.get_session_status.return_value = SessionStatus(
            session_id="s1", total_tokens=500
        )

        host = self._make_host(
            status_provider=mock_provider,
            active_tasks={"telegram:user123": MagicMock()},
        )
        await RouterCommandsMixin._handle_status_command(host, inbound_msg)

        reply = host._bus.publish_outbound.call_args[0][0]
        assert "Running" in reply.content

    @pytest.mark.asyncio
    async def test_status_shows_yolo_mode(self, inbound_msg: InboundMessage) -> None:
        import time

        mock_provider = AsyncMock()
        mock_provider.get_session_status.return_value = SessionStatus(
            session_id="s1", total_tokens=100
        )

        host = self._make_host(
            status_provider=mock_provider,
            session_yolo={"telegram:user123": (time.time(), 300.0)},
        )
        await RouterCommandsMixin._handle_status_command(host, inbound_msg)

        reply = host._bus.publish_outbound.call_args[0][0]
        assert "YOLO" in reply.content
        assert "ON" in reply.content

    @pytest.mark.asyncio
    async def test_status_no_session(self, inbound_msg: InboundMessage) -> None:
        mock_provider = AsyncMock()
        mock_provider.get_session_status.return_value = None

        host = self._make_host(status_provider=mock_provider)
        await RouterCommandsMixin._handle_status_command(host, inbound_msg)

        reply = host._bus.publish_outbound.call_args[0][0]
        assert "No active session" in reply.content

    @pytest.mark.asyncio
    async def test_status_shows_timestamps(self, inbound_msg: InboundMessage) -> None:
        mock_provider = AsyncMock()
        mock_provider.get_session_status.return_value = SessionStatus(
            session_id="s1",
            total_tokens=200,
            created_at="2026-05-20 09:30",
            last_activity="2026-05-20 10:15",
        )
        host = self._make_host(status_provider=mock_provider)
        await RouterCommandsMixin._handle_status_command(host, inbound_msg)

        reply = host._bus.publish_outbound.call_args[0][0]
        assert "2026-05-20 09:30" in reply.content
        assert "2026-05-20 10:15" in reply.content
        assert "Created" in reply.content
        assert "Last Activity" in reply.content

    @pytest.mark.asyncio
    async def test_status_shows_queued_messages(self, inbound_msg: InboundMessage) -> None:
        mock_provider = AsyncMock()
        mock_provider.get_session_status.return_value = SessionStatus(
            session_id="s1", total_tokens=100,
        )
        host = self._make_host(status_provider=mock_provider)
        host._gate.pending_count.return_value = 3

        await RouterCommandsMixin._handle_status_command(host, inbound_msg)

        reply = host._bus.publish_outbound.call_args[0][0]
        assert "Queued" in reply.content
        assert "3" in reply.content

    @pytest.mark.asyncio
    async def test_status_hides_queued_when_zero(self, inbound_msg: InboundMessage) -> None:
        mock_provider = AsyncMock()
        mock_provider.get_session_status.return_value = SessionStatus(
            session_id="s1", total_tokens=100,
        )
        host = self._make_host(status_provider=mock_provider)
        await RouterCommandsMixin._handle_status_command(host, inbound_msg)

        reply = host._bus.publish_outbound.call_args[0][0]
        assert "Queued" not in reply.content

    @pytest.mark.asyncio
    async def test_status_yolo_permanent(self, inbound_msg: InboundMessage) -> None:
        import time

        mock_provider = AsyncMock()
        mock_provider.get_session_status.return_value = SessionStatus(
            session_id="s1", total_tokens=50,
        )
        host = self._make_host(
            status_provider=mock_provider,
            session_yolo={"telegram:user123": (time.time(), None)},
        )
        await RouterCommandsMixin._handle_status_command(host, inbound_msg)

        reply = host._bus.publish_outbound.call_args[0][0]
        assert "YOLO" in reply.content
        assert "ON" in reply.content
        assert "expires" not in reply.content

    @pytest.mark.asyncio
    async def test_status_yolo_expired_cleanup(self, inbound_msg: InboundMessage) -> None:
        mock_provider = AsyncMock()
        mock_provider.get_session_status.return_value = SessionStatus(
            session_id="s1", total_tokens=50,
        )
        yolo_state: dict[str, tuple[float, float | None]] = {
            "telegram:user123": (0.0, 1.0),
        }
        host = self._make_host(
            status_provider=mock_provider,
            session_yolo=yolo_state,
        )
        await RouterCommandsMixin._handle_status_command(host, inbound_msg)

        reply = host._bus.publish_outbound.call_args[0][0]
        assert "YOLO" not in reply.content
        assert "telegram:user123" not in host._session_yolo

    @pytest.mark.asyncio
    async def test_status_group_message(self) -> None:
        group_msg = InboundMessage(
            channel="telegram",
            sender_id="sender456",
            chat_id="group789",
            content="/status",
            is_group=True,
            message_id="msg_id_1",
        )
        mock_provider = AsyncMock()
        mock_provider.get_session_status.return_value = SessionStatus(
            session_id="gs1", total_tokens=3000,
        )
        host = self._make_host(status_provider=mock_provider)
        await RouterCommandsMixin._handle_status_command(host, group_msg)

        mock_provider.get_session_status.assert_called_once_with("telegram", "group789")
        reply = host._bus.publish_outbound.call_args[0][0]
        assert reply.recipient_id == "group789"
        assert reply.reply_to_id == "msg_id_1"

    @pytest.mark.asyncio
    async def test_status_reply_to_via_metadata_message_id(self) -> None:
        """When msg.message_id is None but metadata has message_id, use metadata."""
        group_msg = InboundMessage(
            channel="telegram",
            sender_id="sender1",
            chat_id="group1",
            content="/status",
            is_group=True,
            metadata={"message_id": "meta_msg_42"},
        )
        mock_provider = AsyncMock()
        mock_provider.get_session_status.return_value = SessionStatus(
            session_id="s1", total_tokens=0,
        )
        host = self._make_host(status_provider=mock_provider)
        await RouterCommandsMixin._handle_status_command(host, group_msg)

        reply = host._bus.publish_outbound.call_args[0][0]
        assert reply.reply_to_id == "meta_msg_42"

    @pytest.mark.asyncio
    async def test_status_dm_no_reply_to(self, inbound_msg: InboundMessage) -> None:
        """DM messages should NOT set reply_to_id."""
        mock_provider = AsyncMock()
        mock_provider.get_session_status.return_value = SessionStatus(
            session_id="s1", total_tokens=0,
        )
        host = self._make_host(status_provider=mock_provider)
        await RouterCommandsMixin._handle_status_command(host, inbound_msg)

        reply = host._bus.publish_outbound.call_args[0][0]
        assert reply.reply_to_id is None

    @pytest.mark.asyncio
    async def test_status_yolo_active_with_timeout(self, inbound_msg: InboundMessage) -> None:
        """YOLO with active timeout shows remaining seconds."""
        import time

        mock_provider = AsyncMock()
        mock_provider.get_session_status.return_value = SessionStatus(
            session_id="s1", total_tokens=0,
        )
        host = self._make_host(
            status_provider=mock_provider,
            session_yolo={"telegram:user123": (time.time(), 600.0)},
        )
        await RouterCommandsMixin._handle_status_command(host, inbound_msg)

        reply = host._bus.publish_outbound.call_args[0][0]
        assert "expires" in reply.content
        assert "YOLO" in reply.content

    @pytest.mark.asyncio
    async def test_status_omits_none_fields(self, inbound_msg: InboundMessage) -> None:
        mock_provider = AsyncMock()
        mock_provider.get_session_status.return_value = SessionStatus(
            session_id="s1",
            total_tokens=0,
        )
        host = self._make_host(status_provider=mock_provider)
        await RouterCommandsMixin._handle_status_command(host, inbound_msg)

        reply = host._bus.publish_outbound.call_args[0][0]
        assert "Title" not in reply.content
        assert "Model" not in reply.content
        assert "Created" not in reply.content
        assert "Last Activity" not in reply.content
