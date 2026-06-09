"""Unit tests for Browser Extension Bridge API and service."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.browser.pool.extension_bridge import (
    ExtensionBridgeNotAvailable,
    ExtensionStatus,
    ExtensionTab,
)
from starlette.websockets import WebSocketState

from app.services.extension.bridge import ExtensionBridgeService, get_extension_bridge


class TestExtensionBridgeService:
    """Test ExtensionBridgeService logic."""

    def test_initial_state(self) -> None:
        bridge = ExtensionBridgeService()
        assert bridge.is_connected() is False
        assert bridge.get_authorized_domains() == []

    @pytest.mark.asyncio
    async def test_get_status_disconnected(self) -> None:
        bridge = ExtensionBridgeService()
        status = await bridge.get_status()
        assert status.connected is False
        assert status.extension_version == ""
        assert status.authorized_domains == []
        assert status.available_tabs == []

    @pytest.mark.asyncio
    async def test_set_authorized_domains(self) -> None:
        bridge = ExtensionBridgeService()
        await bridge.set_authorized_domains(["github.com", "*.google.com"])
        assert bridge.get_authorized_domains() == ["github.com", "*.google.com"]

    @pytest.mark.asyncio
    async def test_list_tabs_when_disconnected(self) -> None:
        bridge = ExtensionBridgeService()
        tabs = await bridge.list_tabs()
        assert tabs == []

    @pytest.mark.asyncio
    async def test_connect_when_disconnected_raises(self) -> None:
        bridge = ExtensionBridgeService()
        with pytest.raises(ExtensionBridgeNotAvailable, match="not connected"):
            await bridge.connect()

    @pytest.mark.asyncio
    async def test_connect_to_unauthorized_domain_raises(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        await bridge.set_authorized_domains(["github.com"])

        with pytest.raises(ExtensionBridgeNotAvailable, match="not authorized"):
            await bridge.connect_to_domain("evil.com")

    @pytest.mark.asyncio
    async def test_disconnect_clears_state(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._ws.client_state = MagicMock()
        bridge._tabs = [MagicMock()]

        await bridge.disconnect()
        assert bridge.is_connected() is False
        assert bridge._ws is None
        assert bridge._tabs == []


class TestDomainMatching:
    """Test _match_domain wildcard matching logic."""

    def test_exact_match(self) -> None:
        assert ExtensionBridgeService._match_domain("github.com", ["github.com"]) is True

    def test_exact_no_match(self) -> None:
        assert ExtensionBridgeService._match_domain("evil.com", ["github.com"]) is False

    def test_wildcard_subdomain_match(self) -> None:
        assert ExtensionBridgeService._match_domain("mail.google.com", ["*.google.com"]) is True

    def test_wildcard_deep_subdomain(self) -> None:
        assert ExtensionBridgeService._match_domain("a.b.google.com", ["*.google.com"]) is True

    def test_wildcard_no_match_on_root(self) -> None:
        assert ExtensionBridgeService._match_domain("google.com", ["*.google.com"]) is False

    def test_case_insensitive_exact(self) -> None:
        assert ExtensionBridgeService._match_domain("GitHub.COM", ["github.com"]) is True

    def test_case_insensitive_wildcard(self) -> None:
        assert ExtensionBridgeService._match_domain("MAIL.Google.Com", ["*.google.com"]) is True

    def test_empty_patterns(self) -> None:
        assert ExtensionBridgeService._match_domain("anything.com", []) is False

    def test_multiple_patterns_one_match(self) -> None:
        patterns = ["github.com", "*.google.com", "example.org"]
        assert ExtensionBridgeService._match_domain("mail.google.com", patterns) is True
        assert ExtensionBridgeService._match_domain("example.org", patterns) is True
        assert ExtensionBridgeService._match_domain("evil.com", patterns) is False


class TestPlaywrightSingleton:
    """Test _ensure_playwright lifecycle management."""

    @pytest.mark.asyncio
    async def test_ensure_playwright_creates_instance(self) -> None:
        bridge = ExtensionBridgeService()
        assert bridge._playwright is None

        mock_pw = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.start = AsyncMock(return_value=mock_pw)

        with patch("app.services.extension.bridge.ExtensionBridgeService._ensure_playwright") as mock_ensure:
            mock_ensure.return_value = mock_pw
            pw = await bridge._ensure_playwright()
            assert pw is mock_pw

    @pytest.mark.asyncio
    async def test_ensure_playwright_reuses_instance(self) -> None:
        bridge = ExtensionBridgeService()
        mock_pw = MagicMock()
        bridge._playwright = mock_pw

        pw = await bridge._ensure_playwright()
        assert pw is mock_pw

    @pytest.mark.asyncio
    async def test_disconnect_stops_playwright(self) -> None:
        bridge = ExtensionBridgeService()
        mock_pw = MagicMock()
        mock_pw.stop = AsyncMock()
        bridge._playwright = mock_pw
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._ws.client_state = WebSocketState.DISCONNECTED

        await bridge.disconnect()

        mock_pw.stop.assert_called_once()
        assert bridge._playwright is None


class TestListTabsFiltering:
    """Test list_tabs domain filtering."""

    @pytest.mark.asyncio
    async def test_list_tabs_filters_by_authorized_domains(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._authorized_domains = ["github.com", "*.google.com"]
        bridge._tabs = [
            ExtensionTab(tab_id=1, url="https://github.com/repo", title="GH", domain="github.com", active=True),
            ExtensionTab(tab_id=2, url="https://mail.google.com", title="Gmail", domain="mail.google.com", active=False),
            ExtensionTab(tab_id=3, url="https://evil.com", title="Evil", domain="evil.com", active=False),
        ]

        with patch.object(bridge, "_refresh_tabs", new_callable=AsyncMock):
            tabs = await bridge.list_tabs()

        assert len(tabs) == 2
        assert tabs[0].domain == "github.com"
        assert tabs[1].domain == "mail.google.com"

    @pytest.mark.asyncio
    async def test_list_tabs_empty_when_no_authorized(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._authorized_domains = []
        bridge._tabs = [
            ExtensionTab(tab_id=1, url="https://github.com", title="GH", domain="github.com", active=True),
        ]

        with patch.object(bridge, "_refresh_tabs", new_callable=AsyncMock):
            tabs = await bridge.list_tabs()

        assert tabs == []


class TestConnectToDomainWildcard:
    """Test connect_to_domain with wildcard-authorized domains."""

    @pytest.mark.asyncio
    async def test_wildcard_authorized_domain_passes(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._authorized_domains = ["*.google.com"]

        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
        bridge._playwright = mock_pw

        with patch.object(bridge, "_request_cdp_target", new_callable=AsyncMock) as mock_cdp:
            mock_cdp.return_value = "ws://127.0.0.1:9222/devtools/browser/abc"
            result = await bridge.connect_to_domain("mail.google.com")

        assert result.browser is mock_browser
        assert result.is_managed is False

    @pytest.mark.asyncio
    async def test_connect_to_domain_not_connected_raises(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = False
        bridge._authorized_domains = ["*.google.com"]

        with pytest.raises(ExtensionBridgeNotAvailable, match="not connected"):
            await bridge.connect_to_domain("mail.google.com")


class TestSendRequest:
    """Test _send_request timeout and error handling."""

    @pytest.mark.asyncio
    async def test_send_request_not_connected_raises(self) -> None:
        bridge = ExtensionBridgeService()
        with pytest.raises(ExtensionBridgeNotAvailable, match="not connected"):
            await bridge._send_request("test_action")

    @pytest.mark.asyncio
    async def test_send_request_timeout(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        bridge._ws = mock_ws

        with pytest.raises(ExtensionBridgeNotAvailable, match="timed out"):
            await bridge._send_request("slow_action", timeout=0.05)

        assert "req_1" not in bridge._pending_requests


class TestSetAuthorizedDomainsNotify:
    """Test set_authorized_domains WebSocket notification."""

    @pytest.mark.asyncio
    async def test_notifies_extension_when_connected(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        bridge._ws = mock_ws

        await bridge.set_authorized_domains(["github.com", "*.google.com"])

        mock_ws.send_text.assert_called_once()
        sent = json.loads(mock_ws.send_text.call_args[0][0])
        assert sent["type"] == "set_domains"
        assert sent["domains"] == ["github.com", "*.google.com"]

    @pytest.mark.asyncio
    async def test_no_notification_when_disconnected(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = False
        bridge._ws = None

        await bridge.set_authorized_domains(["example.com"])
        assert bridge.get_authorized_domains() == ["example.com"]

    @pytest.mark.asyncio
    async def test_notification_failure_swallowed(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock(side_effect=RuntimeError("ws broken"))
        bridge._ws = mock_ws

        await bridge.set_authorized_domains(["example.com"])
        assert bridge.get_authorized_domains() == ["example.com"]


class TestReceiveLoop:
    """Test message handling in _receive_loop."""

    @pytest.mark.asyncio
    async def test_hello_message_sets_metadata(self) -> None:
        bridge = ExtensionBridgeService()
        mock_ws = MagicMock()
        msgs = [
            json.dumps({"type": "hello", "version": "1.2.0", "browser": "Chrome"}),
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

    @pytest.mark.asyncio
    async def test_tabs_update_message(self) -> None:
        bridge = ExtensionBridgeService()
        mock_ws = MagicMock()
        tabs_data = [
            {"id": 1, "url": "https://github.com", "title": "GH", "domain": "github.com", "active": True},
            {"id": 2, "url": "https://google.com", "title": "Google", "domain": "google.com", "active": False},
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
    async def test_domains_update_message(self) -> None:
        bridge = ExtensionBridgeService()
        mock_ws = MagicMock()
        msgs = [json.dumps({"type": "domains_update", "domains": ["new.com", "*.new.org"]})]
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

        assert bridge._authorized_domains == ["new.com", "*.new.org"]

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


class TestRequestCdpTarget:
    """Test _request_cdp_target helper."""

    @pytest.mark.asyncio
    async def test_returns_cdp_url(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        bridge._ws = mock_ws

        loop = asyncio.get_running_loop()

        async def set_result_later():
            await asyncio.sleep(0.01)
            req_id = list(bridge._pending_requests.keys())[0]
            bridge._pending_requests[req_id].set_result({"cdp_ws_url": "ws://127.0.0.1:9222/x"})

        task = asyncio.create_task(set_result_later())
        url = await bridge._request_cdp_target(timeout=2.0)
        await task

        assert url == "ws://127.0.0.1:9222/x"

    @pytest.mark.asyncio
    async def test_raises_if_no_url_in_response(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        bridge._ws = mock_ws

        async def set_result_later():
            await asyncio.sleep(0.01)
            req_id = list(bridge._pending_requests.keys())[0]
            bridge._pending_requests[req_id].set_result({"something": "else"})

        task = asyncio.create_task(set_result_later())
        with pytest.raises(ExtensionBridgeNotAvailable, match="did not return CDP"):
            await bridge._request_cdp_target(timeout=2.0)
        await task


class TestExtensionBridgeSingleton:
    """Test singleton access."""

    def test_get_extension_bridge_returns_same_instance(self) -> None:
        bridge1 = get_extension_bridge()
        bridge2 = get_extension_bridge()
        assert bridge1 is bridge2
