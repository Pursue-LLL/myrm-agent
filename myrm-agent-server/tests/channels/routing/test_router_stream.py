from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.router_stream import RouterStreamMixin
from app.channels.types import ProgressUpdate
from app.channels.types.components import ActionButton
from app.channels.types.messages import InboundMessage, OutboundMessage
from app.config.settings import settings
from app.remote_access.pairing import parse_pairing_token


class DummyRouter(RouterStreamMixin):
    def __init__(self, bus):
        self._bus = bus


@pytest.fixture
def mock_bus():
    bus = AsyncMock()
    bus.get_channel = MagicMock(return_value=None)
    return bus


@pytest.fixture
def stream_handler(mock_bus):
    handler = DummyRouter(mock_bus)
    return handler


@pytest.mark.asyncio
async def test_send_interactive_progress_preserves_thread_id(stream_handler, mock_bus):
    msg = InboundMessage(
        channel="telegram",
        chat_id="-100123456789",
        sender_id="123",
        content="/test",
        is_group=True,
        thread_id="456",
        message_id="789",
        metadata={"message_id": "789"},
    )
    progress = ProgressUpdate(label="Working...", quick_replies=None)

    await stream_handler._send_interactive_progress(msg, "-100123456789", progress)

    mock_bus.send_tracked.assert_called_once()
    outbound_msg: OutboundMessage = mock_bus.send_tracked.call_args[0][0]

    assert outbound_msg.thread_id == "456"
    assert outbound_msg.reply_to_id == "789"
    assert outbound_msg.content == "Working..."


@pytest.mark.asyncio
async def test_send_interactive_progress_omits_mobile_button_without_public_url(
    stream_handler,
    mock_bus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_deep_link(_chat_id: str) -> None:
        return None

    monkeypatch.setattr(
        "app.remote_access.mobile_deep_link.resolve_mobile_status_deep_link",
        _no_deep_link,
    )

    msg = InboundMessage(
        channel="feishu",
        chat_id="chat-1",
        sender_id="user-1",
        content="run task",
    )
    progress = ProgressUpdate(label="Approve file delete?", quick_replies=None)

    await stream_handler._send_interactive_progress(msg, "agent-chat-1", progress)

    outbound_msg: OutboundMessage = mock_bus.send_tracked.call_args[0][0]
    assert outbound_msg.components == ()


@pytest.mark.asyncio
async def test_send_interactive_progress_adds_scoped_mobile_deep_link_button(
    stream_handler,
    mock_bus,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings.database, "state_dir", str(tmp_path))
    from app.remote_access.tunnel_manager import TunnelState, TunnelStatus

    class _FakeTunnelManager:
        def status(self) -> TunnelStatus:
            return TunnelStatus(state=TunnelState.RUNNING, public_url="https://abc.trycloudflare.com")

    async def _no_ingress() -> str:
        return ""

    monkeypatch.setattr("app.remote_access.mobile_deep_link.get_tunnel_manager", _FakeTunnelManager)
    monkeypatch.setattr("app.core.infra.ingress.get_public_ingress_base_url", _no_ingress)

    msg = InboundMessage(
        channel="telegram",
        chat_id="channel-peer-1",
        sender_id="user-1",
        content="run task",
    )
    progress = ProgressUpdate(label="Approve browser action?", quick_replies=None)

    await stream_handler._send_interactive_progress(msg, "agent-chat-99", progress)

    outbound_msg: OutboundMessage = mock_bus.send_tracked.call_args[0][0]
    assert len(outbound_msg.components) == 1
    button = outbound_msg.components[0][0]
    assert isinstance(button, ActionButton)
    assert button.action_id == "mobile:open_status"
    assert button.url.startswith("https://abc.trycloudflare.com/mobile/status/agent-chat-99?pair=")

    token = button.url.split("pair=", 1)[1]
    parsed = parse_pairing_token(token)
    assert parsed is not None
    assert parsed["chat_id"] == "agent-chat-99"
