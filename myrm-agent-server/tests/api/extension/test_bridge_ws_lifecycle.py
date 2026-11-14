"""The WebSocket session of ExtensionBridgeService: status broadcast, connection replacement, cleanup, heartbeat."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.browser.pool.extension_bridge import (
    ExtensionBridgeNotAvailable,
)
from starlette.websockets import WebSocketState

from app.services.extension.bridge import ExtensionBridgeService


class TestSSEBroadcast:
    """Test _broadcast_extension_status SSE integration."""

    @pytest.mark.asyncio
    async def test_disconnect_broadcasts_false(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._ws.client_state = WebSocketState.DISCONNECTED
        bridge._tabs = []

        with patch("app.services.extension.bridge.common._broadcast_extension_status") as mock_broadcast:
            await bridge.disconnect()
            mock_broadcast.assert_called_once_with(False)

    @pytest.mark.asyncio
    async def test_broadcast_publishes_correct_event(self) -> None:
        from app.services.extension.bridge import _broadcast_extension_status

        with patch("app.services.extension.bridge.common.get_event_bus") as mock_bus:
            mock_publisher = MagicMock()
            mock_bus.return_value = mock_publisher

            _broadcast_extension_status(True)

            mock_publisher.publish.assert_called_once()
            event = mock_publisher.publish.call_args[0][0]
            assert event.event_type.value == "extension_status_changed"
            assert event.data == {"connected": True}

    @pytest.mark.asyncio
    async def test_broadcast_false_event(self) -> None:
        from app.services.extension.bridge import _broadcast_extension_status

        with patch("app.services.extension.bridge.common.get_event_bus") as mock_bus:
            mock_publisher = MagicMock()
            mock_bus.return_value = mock_publisher

            _broadcast_extension_status(False)

            event = mock_publisher.publish.call_args[0][0]
            assert event.data == {"connected": False}


class TestHandleWsConnectionLifecycle:
    """Cover WebSocket session setup and pending request cleanup."""

    @pytest.mark.asyncio
    async def test_handle_ws_connection_clears_pending_on_exit(self) -> None:
        bridge = ExtensionBridgeService()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        async def stop_receive_loop() -> None:
            return None

        with patch.object(
            bridge,
            "_receive_loop",
            new_callable=AsyncMock,
            side_effect=stop_receive_loop,
        ):
            with patch.object(bridge, "_heartbeat_loop", new_callable=AsyncMock):
                with patch("app.services.extension.bridge.common._broadcast_extension_status") as mock_broadcast:
                    await bridge.handle_ws_connection(mock_ws)

        assert bridge._connected is False
        assert bridge._ws is None
        assert mock_broadcast.call_args_list[0].args[0] is True
        assert mock_broadcast.call_args_list[-1].args[0] is False

    @pytest.mark.asyncio
    async def test_closing_the_connection_resets_the_relay_and_forgets_the_tab_mirror(self) -> None:
        bridge = ExtensionBridgeService()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        async def receive_a_tab_report_then_close() -> None:
            bridge._apply_tab_list([{"id": 4, "url": "about:blank", "agentOwned": True}])

        with (
            patch.object(bridge, "_receive_loop", new_callable=AsyncMock, side_effect=receive_a_tab_report_then_close),
            patch.object(bridge, "_heartbeat_loop", new_callable=AsyncMock),
            patch("app.services.extension.bridge.common.get_cdp_relay_manager") as mock_manager,
        ):
            mock_manager.return_value.bind_extension_transport = AsyncMock()
            await bridge.handle_ws_connection(mock_ws)

        mock_manager.return_value.bind_extension_transport.assert_awaited_once_with(None)
        assert bridge._tabs == []
        assert bridge._agent_tabs == {}

    @pytest.mark.asyncio
    async def test_a_replaced_connection_does_not_reset_its_successor(self) -> None:
        bridge = ExtensionBridgeService()
        successor = MagicMock()
        bridge._ws = successor
        bridge._connected = True
        bridge._apply_tab_list([{"id": 4, "url": "about:blank", "agentOwned": True}])

        with patch("app.services.extension.bridge.common.get_cdp_relay_manager") as mock_manager:
            mock_manager.return_value.bind_extension_transport = AsyncMock()
            await bridge._release_connection(MagicMock())

        mock_manager.return_value.bind_extension_transport.assert_not_awaited()
        assert bridge._ws is successor
        assert bridge._connected is True
        assert bridge._agent_tabs == {4: None}


class TestHandleWsConnectionPendingCleanup:
    """Cover pending request cancellation when WS session ends."""

    @pytest.mark.asyncio
    async def test_pending_requests_get_connection_lost_error(self) -> None:
        bridge = ExtensionBridgeService()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        loop = asyncio.get_running_loop()
        pending: asyncio.Future[object] = loop.create_future()
        bridge._pending_requests["req_pending"] = pending

        async def stop_receive_loop() -> None:
            return None

        with patch.object(
            bridge,
            "_receive_loop",
            new_callable=AsyncMock,
            side_effect=stop_receive_loop,
        ):
            with patch.object(bridge, "_heartbeat_loop", new_callable=AsyncMock):
                await bridge.handle_ws_connection(mock_ws)

        assert pending.done()
        with pytest.raises(ExtensionBridgeNotAvailable, match="Connection lost"):
            pending.result()


class TestHandleWsConnectionReplaceExisting:
    """Cover reconnect replacing an existing websocket session."""

    @pytest.mark.asyncio
    async def test_handle_ws_connection_disconnects_previous_socket(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._ws = MagicMock()
        bridge._connected = True

        new_ws = MagicMock()
        new_ws.accept = AsyncMock()

        with patch.object(bridge, "disconnect", new_callable=AsyncMock) as mock_disconnect:
            with patch.object(bridge, "_receive_loop", new_callable=AsyncMock):
                with patch.object(bridge, "_heartbeat_loop", new_callable=AsyncMock):
                    await bridge.handle_ws_connection(new_ws)

        mock_disconnect.assert_awaited_once()


class TestDisconnectCancelsBackgroundTasks:
    """Cover disconnect() cancellation of heartbeat/receive tasks."""

    @pytest.mark.asyncio
    async def test_disconnect_cancels_heartbeat_and_receive_tasks(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._ws.client_state = WebSocketState.DISCONNECTED

        async def idle_forever() -> None:
            await asyncio.sleep(3600)

        bridge._heartbeat_task = asyncio.create_task(idle_forever())
        bridge._receive_task = asyncio.create_task(idle_forever())

        await bridge.disconnect()
        await asyncio.sleep(0)

        assert bridge._heartbeat_task.cancelled()
        assert bridge._receive_task.cancelled()


class TestHandleWsConnectionCancelledReceive:
    """Cover CancelledError branch in handle_ws_connection."""

    @pytest.mark.asyncio
    async def test_handle_ws_connection_swallows_cancelled_receive(self) -> None:
        bridge = ExtensionBridgeService()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        async def raise_cancelled() -> None:
            raise asyncio.CancelledError

        with patch.object(bridge, "_receive_loop", new_callable=AsyncMock, side_effect=raise_cancelled):
            with patch.object(bridge, "_heartbeat_loop", new_callable=AsyncMock):
                await bridge.handle_ws_connection(mock_ws)

        assert bridge._connected is False


class TestHeartbeatLoopPing:
    """Cover heartbeat loop ping send path without long waits."""

    @pytest.mark.asyncio
    async def test_heartbeat_loop_sends_ping_then_stops(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        bridge._ws = mock_ws
        bridge._last_heartbeat = time.monotonic()

        sleep_calls = 0

        async def fake_sleep(_seconds: float) -> None:
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                bridge._connected = False

        with patch("app.services.extension.bridge.relay.asyncio.sleep", side_effect=fake_sleep):
            await bridge._heartbeat_loop()

        mock_ws.send_text.assert_awaited_once()
