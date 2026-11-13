"""The receive loop of ExtensionBridgeService: how each message the extension sends is handled."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest
from myrm_agent_harness.toolkits.browser.pool.extension_bridge import (
    ExtensionBridgeNotAvailable,
)
from starlette.websockets import WebSocketDisconnect

from app.services.extension.bridge import ExtensionBridgeService
from tests.support.extension_fake_socket import FakeWs


class TestReceiveLoop:
    """Test message handling in _receive_loop."""

    @pytest.mark.asyncio
    async def test_hello_message_sets_metadata(self) -> None:
        bridge = ExtensionBridgeService()
        mock_ws = MagicMock()
        msgs = [
            json.dumps(
                {
                    "type": "hello",
                    "version": "1.2.0",
                    "browser": "Chrome",
                    "capabilities": ["navigate_url", "list_tabs"],
                }
            ),
        ]
        call_count = 0

        async def fake_receive():
            nonlocal call_count
            if call_count < len(msgs):
                msg = msgs[call_count]
                call_count += 1
                return msg
            raise Exception("stop")

        mock_ws.receive_text = fake_receive
        bridge._ws = mock_ws

        await bridge._receive_loop()

        assert bridge._extension_version == "1.2.0"
        assert bridge._browser_name == "Chrome"
        assert bridge._hello_received is True
        assert bridge._capabilities == {"navigate_url", "list_tabs"}

    @pytest.mark.asyncio
    async def test_tabs_update_message(self) -> None:
        bridge = ExtensionBridgeService()
        mock_ws = MagicMock()
        tabs_data = [
            {
                "id": 1,
                "url": "https://github.com",
                "title": "GH",
                "domain": "github.com",
                "active": True,
            },
            {
                "id": 2,
                "url": "https://google.com",
                "title": "Google",
                "domain": "google.com",
                "active": False,
            },
        ]
        msgs = [json.dumps({"type": "tabs_update", "tabs": tabs_data})]
        call_count = 0

        async def fake_receive():
            nonlocal call_count
            if call_count < len(msgs):
                msg = msgs[call_count]
                call_count += 1
                return msg
            raise Exception("stop")

        mock_ws.receive_text = fake_receive
        bridge._ws = mock_ws

        await bridge._receive_loop()

        assert len(bridge._tabs) == 2
        assert bridge._tabs[0].tab_id == 1
        assert bridge._tabs[0].domain == "github.com"

    @pytest.mark.asyncio
    async def test_response_resolves_future(self) -> None:
        bridge = ExtensionBridgeService()
        mock_ws = MagicMock()
        msgs = [json.dumps({"type": "response", "id": "req_1", "data": {"cdp_ws_url": "ws://x"}})]
        call_count = 0

        async def fake_receive():
            nonlocal call_count
            if call_count < len(msgs):
                msg = msgs[call_count]
                call_count += 1
                return msg
            raise Exception("stop")

        mock_ws.receive_text = fake_receive
        bridge._ws = mock_ws

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[object] = loop.create_future()
        bridge._pending_requests["req_1"] = fut

        await bridge._receive_loop()

        assert fut.done()
        assert fut.result() == {"cdp_ws_url": "ws://x"}

    @pytest.mark.asyncio
    async def test_response_error_sets_exception(self) -> None:
        bridge = ExtensionBridgeService()
        mock_ws = MagicMock()
        msgs = [json.dumps({"type": "response", "id": "req_2", "error": "debugger failed"})]
        call_count = 0

        async def fake_receive():
            nonlocal call_count
            if call_count < len(msgs):
                msg = msgs[call_count]
                call_count += 1
                return msg
            raise Exception("stop")

        mock_ws.receive_text = fake_receive
        bridge._ws = mock_ws

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[object] = loop.create_future()
        bridge._pending_requests["req_2"] = fut

        await bridge._receive_loop()

        assert fut.done()
        with pytest.raises(ExtensionBridgeNotAvailable, match="debugger failed"):
            fut.result()

    @pytest.mark.asyncio
    async def test_pong_updates_heartbeat(self) -> None:
        bridge = ExtensionBridgeService()
        mock_ws = MagicMock()
        bridge._last_heartbeat = 0.0
        msgs = [json.dumps({"type": "pong"})]
        call_count = 0

        async def fake_receive():
            nonlocal call_count
            if call_count < len(msgs):
                msg = msgs[call_count]
                call_count += 1
                return msg
            raise Exception("stop")

        mock_ws.receive_text = fake_receive
        bridge._ws = mock_ws

        await bridge._receive_loop()

        assert bridge._last_heartbeat > 0.0

    @pytest.mark.asyncio
    async def test_a_retired_message_type_is_ignored_and_later_messages_still_work(self) -> None:
        """An older extension may still send message types the server dropped; that must not cost it the connection."""
        bridge = ExtensionBridgeService()
        bridge._ws = FakeWs(
            [
                json.dumps({"type": "domains_update", "domains": ["example.com"]}),
                json.dumps(
                    {
                        "type": "hello",
                        "version": "0.9.0",
                        "browser": "Chrome",
                        "capabilities": ["navigate_url", "list_tabs", "attach_debugger", "detach_debugger"],
                    }
                ),
            ]
        )

        await bridge._receive_loop()

        assert bridge._hello_received is True
        assert bridge._authorized_domains == []
        assert bridge._capabilities >= {"navigate_url", "list_tabs"}
        bridge._require_action_capability("navigate_url")


class TestReceiveLoopDisconnect:
    """Cover receive loop disconnect and error branches."""

    @pytest.mark.asyncio
    async def test_receive_loop_handles_client_disconnect(self) -> None:
        bridge = ExtensionBridgeService()
        mock_ws = MagicMock()

        async def raise_disconnect() -> str:
            raise WebSocketDisconnect()

        mock_ws.receive_text = raise_disconnect
        bridge._ws = mock_ws

        await bridge._receive_loop()
