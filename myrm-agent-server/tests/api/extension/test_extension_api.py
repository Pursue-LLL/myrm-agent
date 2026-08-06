"""Unit tests for Browser Extension Bridge API and service."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.browser.pool.extension_bridge import (
    ExtensionBridgeNotAvailable,
    ExtensionTab,
)
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect, WebSocketState

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
        assert status.handshake_ready is False
        assert status.extension_version == ""
        assert status.authorized_domains == []
        assert status.available_tabs == []
        assert status.capabilities == []

    @pytest.mark.asyncio
    async def test_get_status_includes_handshake_ready(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._hello_received = True
        bridge._capabilities = {"navigate_url", "list_tabs"}

        status = await bridge.get_status()

        assert status.connected is True
        assert status.handshake_ready is True
        assert status.capabilities == ["list_tabs", "navigate_url"]

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


class TestSSEBroadcast:
    """Test _broadcast_extension_status SSE integration."""

    @pytest.mark.asyncio
    async def test_disconnect_broadcasts_false(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._ws.client_state = WebSocketState.DISCONNECTED
        bridge._tabs = []

        with patch(
            "app.services.extension.bridge._broadcast_extension_status"
        ) as mock_broadcast:
            await bridge.disconnect()
            mock_broadcast.assert_called_once_with(False)

    @pytest.mark.asyncio
    async def test_broadcast_publishes_correct_event(self) -> None:
        from app.services.extension.bridge import _broadcast_extension_status

        with patch("app.services.extension.bridge.get_event_bus") as mock_bus:
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

        with patch("app.services.extension.bridge.get_event_bus") as mock_bus:
            mock_publisher = MagicMock()
            mock_bus.return_value = mock_publisher

            _broadcast_extension_status(False)

            event = mock_publisher.publish.call_args[0][0]
            assert event.data == {"connected": False}


class TestDomainMatching:
    """Test _match_domain wildcard matching logic."""

    def test_exact_match(self) -> None:
        assert (
            ExtensionBridgeService._match_domain("github.com", ["github.com"]) is True
        )

    def test_exact_no_match(self) -> None:
        assert ExtensionBridgeService._match_domain("evil.com", ["github.com"]) is False

    def test_wildcard_subdomain_match(self) -> None:
        assert (
            ExtensionBridgeService._match_domain("mail.google.com", ["*.google.com"])
            is True
        )

    def test_wildcard_deep_subdomain(self) -> None:
        assert (
            ExtensionBridgeService._match_domain("a.b.google.com", ["*.google.com"])
            is True
        )

    def test_wildcard_matches_root(self) -> None:
        assert (
            ExtensionBridgeService._match_domain("google.com", ["*.google.com"]) is True
        )

    def test_case_insensitive_exact(self) -> None:
        assert (
            ExtensionBridgeService._match_domain("GitHub.COM", ["github.com"]) is True
        )

    def test_case_insensitive_wildcard(self) -> None:
        assert (
            ExtensionBridgeService._match_domain("MAIL.Google.Com", ["*.google.com"])
            is True
        )

    def test_empty_patterns(self) -> None:
        assert ExtensionBridgeService._match_domain("anything.com", []) is False

    def test_multiple_patterns_one_match(self) -> None:
        patterns = ["github.com", "*.google.com", "example.org"]
        assert ExtensionBridgeService._match_domain("mail.google.com", patterns) is True
        assert ExtensionBridgeService._match_domain("example.org", patterns) is True
        assert ExtensionBridgeService._match_domain("evil.com", patterns) is False

    def test_wildcard_warning_for_implicit_root(self) -> None:
        warnings = ExtensionBridgeService.analyze_domain_policy_warnings(
            ["*.google.com"]
        )
        assert len(warnings) == 1
        assert warnings[0].code == "wildcard_includes_root"
        assert warnings[0].pattern == "*.google.com"
        assert warnings[0].root_domain == "google.com"

    def test_wildcard_warning_suppressed_when_root_explicit(self) -> None:
        warnings = ExtensionBridgeService.analyze_domain_policy_warnings(
            ["*.google.com", "google.com"]
        )
        assert warnings == []


class TestPlaywrightSingleton:
    """Test _ensure_playwright lifecycle management."""

    @pytest.mark.asyncio
    async def test_ensure_playwright_creates_instance(self) -> None:
        bridge = ExtensionBridgeService()
        assert bridge._playwright is None

        mock_pw = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.start = AsyncMock(return_value=mock_pw)

        with patch(
            "app.services.extension.bridge.ExtensionBridgeService._ensure_playwright"
        ) as mock_ensure:
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
            ExtensionTab(
                tab_id=1,
                url="https://github.com/repo",
                title="GH",
                domain="github.com",
                active=True,
            ),
            ExtensionTab(
                tab_id=2,
                url="https://mail.google.com",
                title="Gmail",
                domain="mail.google.com",
                active=False,
            ),
            ExtensionTab(
                tab_id=3,
                url="https://evil.com",
                title="Evil",
                domain="evil.com",
                active=False,
            ),
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
            ExtensionTab(
                tab_id=1,
                url="https://github.com",
                title="GH",
                domain="github.com",
                active=True,
            ),
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
        bridge._cdp_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"

        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
        bridge._playwright = mock_pw

        with patch.object(
            bridge, "_request_debugger_attach", new_callable=AsyncMock
        ) as mock_attach:
            mock_attach.return_value = 42
            result = await bridge.connect_to_domain("mail.google.com")

        assert result.browser is mock_browser
        assert result.is_managed is False

    @pytest.mark.asyncio
    async def test_wildcard_authorized_root_domain_passes(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._authorized_domains = ["*.google.com"]
        bridge._cdp_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"

        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
        bridge._playwright = mock_pw

        with patch.object(
            bridge, "_request_debugger_attach", new_callable=AsyncMock
        ) as mock_attach:
            mock_attach.return_value = 42
            result = await bridge.connect_to_domain("google.com")

        assert result.browser is mock_browser
        assert result.is_managed is False

    @pytest.mark.asyncio
    async def test_connect_to_domain_not_connected_raises(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = False
        bridge._authorized_domains = ["*.google.com"]

        with pytest.raises(ExtensionBridgeNotAvailable, match="not connected"):
            await bridge.connect_to_domain("mail.google.com")


class TestNavigateToUrl:
    """Test navigate_to_url extension flow (no direct CDP requirement)."""

    @pytest.mark.asyncio
    async def test_navigate_to_url_success(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._capabilities = {"navigate_url"}
        bridge._authorized_domains = ["*.corp.local"]
        bridge._send_request = AsyncMock(
            return_value={
                "tabId": 42,
                "url": "http://portal.corp.local/dashboard",
                "title": "Dashboard",
                "domain": "portal.corp.local",
                "active": False,
            }
        )

        tab = await bridge.navigate_to_url(
            "http://portal.corp.local/dashboard",
            domain="portal.corp.local",
        )

        assert tab.tab_id == 42
        assert tab.domain == "portal.corp.local"
        assert tab.title == "Dashboard"

    @pytest.mark.asyncio
    async def test_navigate_to_url_requires_extension_capability(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._capabilities = set()
        bridge._authorized_domains = ["*.corp.local"]

        with pytest.raises(
            ExtensionBridgeNotAvailable, match="missing required capability"
        ):
            await bridge.navigate_to_url("http://portal.corp.local/dashboard")

    @pytest.mark.asyncio
    async def test_navigate_to_url_requires_hello_handshake(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = False
        bridge._capabilities = {"navigate_url"}
        bridge._authorized_domains = ["*.corp.local"]

        with pytest.raises(
            ExtensionBridgeNotAvailable, match="handshake is not completed"
        ):
            await bridge.navigate_to_url("http://portal.corp.local/dashboard")

    @pytest.mark.asyncio
    async def test_navigate_to_url_rejects_unauthorized_domain(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._authorized_domains = ["*.corp.local"]

        with pytest.raises(ExtensionBridgeNotAvailable, match="not authorized"):
            await bridge.navigate_to_url("http://evil.local/internal")

    @pytest.mark.asyncio
    async def test_navigate_to_url_rejects_domain_url_mismatch(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._authorized_domains = ["*.corp.local"]

        with pytest.raises(
            ExtensionBridgeNotAvailable, match="does not match navigation target"
        ):
            await bridge.navigate_to_url(
                "http://portal.corp.local/dashboard",
                domain="evil.local",
            )


class TestActionCapabilityContract:
    """Test action-level capability enforcement for extension relay actions."""

    @pytest.mark.asyncio
    async def test_send_request_requires_mapped_capability(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._capabilities = set()

        with pytest.raises(
            ExtensionBridgeNotAvailable, match="missing required capability 'list_tabs'"
        ):
            await bridge._send_request("list_tabs")

    @pytest.mark.asyncio
    async def test_send_request_allows_unmapped_action_without_capability(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        bridge._ws = mock_ws
        bridge._hello_received = True
        bridge._capabilities = set()

        with pytest.raises(ExtensionBridgeNotAvailable, match="timed out"):
            await bridge._send_request("heartbeat_probe", timeout=0.05)

    @pytest.mark.asyncio
    async def test_request_debugger_attach_requires_capability(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._capabilities = set()

        with pytest.raises(
            ExtensionBridgeNotAvailable,
            match="missing required capability 'attach_debugger'",
        ):
            await bridge._request_debugger_attach(domain="example.com")

    @pytest.mark.asyncio
    async def test_send_request_requires_detach_debugger_capability(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._capabilities = {"attach_debugger"}

        with pytest.raises(
            ExtensionBridgeNotAvailable,
            match="missing required capability 'detach_debugger'",
        ):
            await bridge._send_request("detach_debugger", {"tabId": 42})

    @pytest.mark.asyncio
    async def test_send_request_detach_debugger_roundtrip(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._hello_received = True
        bridge._capabilities = {"detach_debugger"}
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        bridge._ws = mock_ws

        async def set_result_later() -> None:
            await asyncio.sleep(0.01)
            req_id = list(bridge._pending_requests.keys())[0]
            bridge._pending_requests[req_id].set_result({"detached": True, "tabId": 42})

        task = asyncio.create_task(set_result_later())
        result = await bridge._send_request("detach_debugger", {"tabId": 42}, timeout=2.0)
        await task

        assert result == {"detached": True, "tabId": 42}


class TestDirectCdpRiskGovernance:
    """Test explicit direct CDP risk warning emission."""

    @pytest.mark.asyncio
    async def test_connect_warns_once_when_using_direct_cdp(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._cdp_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"

        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
        bridge._playwright = mock_pw

        with patch.object(
            bridge, "_request_debugger_attach", new_callable=AsyncMock
        ) as mock_attach:
            mock_attach.return_value = 42
            with patch("app.services.extension.bridge.logger.warning") as mock_warning:
                await bridge.connect()
                await bridge.connect()

        mock_warning.assert_called_once()


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
        msgs = [
            json.dumps(
                {"type": "response", "id": "req_1", "data": {"cdp_ws_url": "ws://x"}}
            )
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
        msgs = [
            json.dumps({"type": "response", "id": "req_2", "error": "debugger failed"})
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
        msgs = [
            json.dumps({"type": "domains_update", "domains": ["new.com", "*.new.org"]})
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


class TestRequestDebuggerAttach:
    """Test _request_debugger_attach helper."""

    @pytest.mark.asyncio
    async def test_returns_tab_id(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._hello_received = True
        bridge._capabilities = {"attach_debugger"}
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        bridge._ws = mock_ws

        async def set_result_later():
            await asyncio.sleep(0.01)
            req_id = list(bridge._pending_requests.keys())[0]
            bridge._pending_requests[req_id].set_result({"tabId": 42})

        task = asyncio.create_task(set_result_later())
        tab_id = await bridge._request_debugger_attach(
            domain="example.com", timeout=2.0
        )
        await task

        assert tab_id == 42

    @pytest.mark.asyncio
    async def test_raises_if_no_tab_id_in_response(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._hello_received = True
        bridge._capabilities = {"attach_debugger"}
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        bridge._ws = mock_ws

        async def set_result_later():
            await asyncio.sleep(0.01)
            req_id = list(bridge._pending_requests.keys())[0]
            bridge._pending_requests[req_id].set_result({"something": "else"})

        task = asyncio.create_task(set_result_later())
        with pytest.raises(
            ExtensionBridgeNotAvailable, match="did not return attached tab ID"
        ):
            await bridge._request_debugger_attach(domain="example.com", timeout=2.0)
        await task


class TestExtensionBridgeSingleton:
    """Test singleton access."""

    def test_get_extension_bridge_returns_same_instance(self) -> None:
        bridge1 = get_extension_bridge()
        bridge2 = get_extension_bridge()
        assert bridge1 is bridge2


class TestExtensionRouterGuards:
    """Test extension WebSocket guardrails in API router."""

    def test_origin_guard_accepts_extension_and_empty(self) -> None:
        from app.api.extension.router import _is_allowed_extension_origin

        assert _is_allowed_extension_origin("chrome-extension://abcdef") is True
        assert _is_allowed_extension_origin("") is True
        assert _is_allowed_extension_origin(None) is True

    def test_origin_guard_rejects_web_origins(self) -> None:
        from app.api.extension.router import _is_allowed_extension_origin

        assert _is_allowed_extension_origin("https://evil.example.com") is False
        assert _is_allowed_extension_origin("http://localhost:3000") is False

    @pytest.mark.asyncio
    async def test_extension_ws_rejects_forbidden_origin(self) -> None:
        from app.api.extension.router import extension_ws

        websocket = MagicMock()
        websocket.headers = {"origin": "https://evil.example.com"}
        websocket.close = AsyncMock()

        await extension_ws(websocket, token="")

        websocket.close.assert_awaited_once_with(code=4003, reason="Forbidden origin")

    @pytest.mark.asyncio
    async def test_extension_ws_requires_token_in_remote_mode(self) -> None:
        from app.api.extension.router import extension_ws

        websocket = MagicMock()
        websocket.headers = {"origin": "chrome-extension://abcdef"}
        websocket.close = AsyncMock()

        with (
            patch("app.config.deploy_mode.is_webui_remote_mode", return_value=True),
            patch(
                "app.config.settings.settings.extension_auth_token", new=SecretStr("")
            ),
        ):
            await extension_ws(websocket, token="")

        websocket.close.assert_awaited_once_with(
            code=4002, reason="Extension auth token required in remote mode"
        )

    @pytest.mark.asyncio
    async def test_extension_ws_accepts_valid_extension_origin_and_token(self) -> None:
        from app.api.extension.router import extension_ws

        websocket = MagicMock()
        websocket.headers = {"origin": "chrome-extension://abcdef"}
        websocket.close = AsyncMock()

        bridge = MagicMock()
        bridge.handle_ws_connection = AsyncMock()

        with (
            patch("app.config.deploy_mode.is_webui_remote_mode", return_value=False),
            patch(
                "app.config.settings.settings.extension_auth_token", new=SecretStr("")
            ),
            patch("app.api.extension.router.get_extension_bridge", return_value=bridge),
        ):
            await extension_ws(websocket, token="")

        bridge.handle_ws_connection.assert_awaited_once_with(websocket)
        websocket.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_extension_ws_rejects_invalid_token(self) -> None:
        from app.api.extension.router import extension_ws

        websocket = MagicMock()
        websocket.headers = {"origin": "chrome-extension://abcdef"}
        websocket.close = AsyncMock()

        with patch(
            "app.config.settings.settings.extension_auth_token",
            new=SecretStr("secret-token"),
        ):
            await extension_ws(websocket, token="wrong-token")

        websocket.close.assert_awaited_once_with(code=4001, reason="Invalid token")


class TestExtensionRouterDomainsAndTabs:
    """Cover REST endpoints for domains, tabs, and disconnect."""

    @pytest.mark.asyncio
    async def test_get_authorized_domains_returns_warnings(self) -> None:
        from app.api.extension.router import get_authorized_domains

        bridge = MagicMock()
        bridge.get_authorized_domains.return_value = ["*.example.com"]
        bridge.analyze_domain_policy_warnings.return_value = (
            ExtensionBridgeService.analyze_domain_policy_warnings(["*.example.com"])
        )

        with patch(
            "app.api.extension.router.get_extension_bridge", return_value=bridge
        ):
            response = await get_authorized_domains()

        assert response.authorized_domains == ["*.example.com"]
        assert len(response.warnings) == 1

    @pytest.mark.asyncio
    async def test_list_extension_tabs_maps_bridge_tabs(self) -> None:
        from app.api.extension.router import list_extension_tabs

        bridge = MagicMock()
        bridge.list_tabs = AsyncMock(
            return_value=[
                ExtensionTab(
                    tab_id=3,
                    url="https://github.com",
                    title="GitHub",
                    domain="github.com",
                    active=True,
                )
            ]
        )

        with patch(
            "app.api.extension.router.get_extension_bridge", return_value=bridge
        ):
            tabs = await list_extension_tabs()

        assert len(tabs) == 1
        assert tabs[0].tab_id == 3
        assert tabs[0].active is True

    @pytest.mark.asyncio
    async def test_disconnect_extension_calls_bridge(self) -> None:
        from app.api.extension.router import disconnect_extension

        bridge = MagicMock()
        bridge.disconnect = AsyncMock()

        with patch(
            "app.api.extension.router.get_extension_bridge", return_value=bridge
        ):
            response = await disconnect_extension()

        bridge.disconnect.assert_awaited_once()
        assert response == {"status": "disconnected"}


class TestExtensionRouterHints:
    """Test extension setup hints API responses."""

    @pytest.mark.asyncio
    async def test_setup_hints_remote_requires_token(self) -> None:
        from app.api.extension.router import get_extension_setup_hints

        bridge = MagicMock()
        bridge.has_direct_cdp_endpoint.return_value = False

        with (
            patch("app.api.extension.router.get_extension_bridge", return_value=bridge),
            patch("app.config.deploy_mode.is_webui_remote_mode", return_value=True),
            patch(
                "app.config.settings.settings.extension_auth_token", new=SecretStr("")
            ),
        ):
            hints = await get_extension_setup_hints()

        assert hints.auth_token_configured is False
        assert hints.auth_token_required is True
        assert hints.cdp_endpoint_discovered is False
        bridge.has_direct_cdp_endpoint.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_setup_hints_local_token_optional(self) -> None:
        from app.api.extension.router import get_extension_setup_hints

        bridge = MagicMock()
        bridge.has_direct_cdp_endpoint.return_value = True

        with (
            patch("app.api.extension.router.get_extension_bridge", return_value=bridge),
            patch("app.config.deploy_mode.is_webui_remote_mode", return_value=False),
            patch(
                "app.config.settings.settings.extension_auth_token",
                new=SecretStr("abc"),
            ),
        ):
            hints = await get_extension_setup_hints()

        assert hints.auth_token_configured is True
        assert hints.auth_token_required is False
        assert hints.cdp_endpoint_discovered is True

    @pytest.mark.asyncio
    async def test_update_domains_returns_policy_warning(self) -> None:
        from app.api.extension.router import (
            DomainsUpdateRequest,
            update_authorized_domains,
        )

        bridge = MagicMock()
        bridge.set_authorized_domains = AsyncMock()
        bridge.get_authorized_domains.return_value = ["*.example.com"]
        bridge.analyze_domain_policy_warnings.return_value = (
            ExtensionBridgeService.analyze_domain_policy_warnings(["*.example.com"])
        )

        with patch(
            "app.api.extension.router.get_extension_bridge", return_value=bridge
        ):
            response = await update_authorized_domains(
                DomainsUpdateRequest(domains=["*.example.com"])
            )

        assert response.authorized_domains == ["*.example.com"]
        assert len(response.warnings) == 1
        assert response.warnings[0].code == "wildcard_includes_root"
        assert response.warnings[0].root_domain == "example.com"


class TestExtensionRouterStatus:
    """Test extension status response shape."""

    @pytest.mark.asyncio
    async def test_status_includes_capabilities(self) -> None:
        from app.api.extension.router import get_extension_status

        bridge = MagicMock()
        bridge.get_status = AsyncMock(
            return_value=SimpleNamespace(
                connected=True,
                handshake_ready=True,
                extension_version="1.2.3",
                browser_name="Chrome",
                authorized_domains=["corp.local"],
                capabilities=[
                    "navigate_url",
                    "list_tabs",
                    "attach_debugger",
                    "detach_debugger",
                ],
                available_tabs=[],
            )
        )

        with patch(
            "app.api.extension.router.get_extension_bridge", return_value=bridge
        ):
            status = await get_extension_status()

        assert status.connected is True
        assert status.handshake_ready is True
        assert status.capabilities == [
            "navigate_url",
            "list_tabs",
            "attach_debugger",
            "detach_debugger",
        ]


class TestExtensionRouterClipAgent:
    """Test wiki clip agent sync REST endpoints."""

    @pytest.mark.asyncio
    async def test_get_clip_agent_returns_config(self) -> None:
        from app.api.extension.routes.clip_agent import get_extension_clip_agent
        from app.services.extension.clip import ExtensionClipAgentConfig

        with patch(
            "app.api.extension.routes.clip_agent.get_extension_clip_agent_config",
            new_callable=AsyncMock,
            return_value=ExtensionClipAgentConfig(
                agent_id="agent-1",
                web_ui_origin="http://localhost:3000",
            ),
        ):
            response = await get_extension_clip_agent()

        assert response.agent_id == "agent-1"
        assert response.web_ui_origin == "http://localhost:3000"

    @pytest.mark.asyncio
    async def test_update_clip_agent_persists_and_notifies_extension(self) -> None:
        from app.api.extension.routes.clip_agent import (
            ExtensionClipAgentUpdateRequest,
            update_extension_clip_agent,
        )
        from app.services.extension.clip import ExtensionClipAgentConfig

        bridge = MagicMock()
        bridge.notify_clip_agent_config = AsyncMock()

        with (
            patch(
                "app.api.extension.routes.clip_agent.set_extension_clip_agent_config",
                new_callable=AsyncMock,
                return_value=ExtensionClipAgentConfig(
                    agent_id="writer",
                    web_ui_origin="http://localhost:3000",
                ),
            ),
            patch(
                "app.api.extension.routes.clip_agent.get_extension_bridge",
                return_value=bridge,
            ),
        ):
            response = await update_extension_clip_agent(
                ExtensionClipAgentUpdateRequest(
                    agent_id="writer",
                    web_ui_origin="http://localhost:3000",
                )
            )

        assert response.agent_id == "writer"
        bridge.notify_clip_agent_config.assert_awaited_once_with(
            "writer",
            "http://localhost:3000",
        )


class TestExtensionBridgeClipAgentNotify:
    @pytest.mark.asyncio
    async def test_notify_clip_agent_config_sends_ws_message(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        bridge._ws = mock_ws

        await bridge.notify_clip_agent_config("agent-9", "http://localhost:3000")

        mock_ws.send_text.assert_awaited_once()
        sent = json.loads(mock_ws.send_text.call_args[0][0])
        assert sent["type"] == "clip_agent_update"
        assert sent["agent_id"] == "agent-9"
        assert sent["web_ui_origin"] == "http://localhost:3000"

    @pytest.mark.asyncio
    async def test_notify_clip_agent_config_skips_when_disconnected(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = False
        bridge._ws = None

        await bridge.notify_clip_agent_config("agent-9", "http://localhost:3000")


class TestMatchDomainEdgeCases:
    """Cover wildcard and empty-input branches in _match_domain."""

    def test_empty_domain_returns_false(self) -> None:
        assert ExtensionBridgeService._match_domain("", ["example.com"]) is False

    def test_empty_pattern_is_skipped(self) -> None:
        assert (
            ExtensionBridgeService._match_domain("example.com", ["", "example.com"])
            is True
        )

    def test_bare_wildcard_pattern_is_skipped(self) -> None:
        assert ExtensionBridgeService._match_domain("example.com", ["*."]) is False


class TestNormalizeCapabilities:
    """Cover capability normalization used by hello handshake."""

    def test_non_list_payload_returns_empty_set(self) -> None:
        assert ExtensionBridgeService._normalize_capabilities("navigate_url") == set()

    def test_mixed_payload_normalizes_tokens(self) -> None:
        caps = ExtensionBridgeService._normalize_capabilities(
            [" Navigate_URL ", "", 42, "list_tabs"]
        )
        assert caps == {"navigate_url", "list_tabs"}


class TestDomainPolicyWarningNormalization:
    """Cover duplicate/empty filtering in analyze_domain_policy_warnings."""

    def test_deduplicates_and_skips_empty_entries(self) -> None:
        warnings = ExtensionBridgeService.analyze_domain_policy_warnings(
            ["", " *.example.com ", "*.example.com", "example.com"]
        )
        assert warnings == []


class TestHasDirectCdpEndpoint:
    """Cover CDP endpoint discovery and negative caching."""

    def test_returns_true_when_cached(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._cdp_endpoint = "ws://127.0.0.1:9222/devtools/browser/test"
        assert bridge.has_direct_cdp_endpoint() is True

    def test_negative_probe_uses_ttl(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._last_cdp_probe_monotonic = time.monotonic()
        with patch.object(bridge, "_resolve_cdp_endpoint") as mock_resolve:
            assert bridge.has_direct_cdp_endpoint(probe_ttl_s=60.0) is False
            mock_resolve.assert_not_called()


class TestNavigateToUrlAdditionalErrors:
    """Cover navigate_to_url validation and malformed extension responses."""

    @pytest.mark.asyncio
    async def test_rejects_url_without_hostname(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._authorized_domains = ["example.com"]

        with pytest.raises(
            ExtensionBridgeNotAvailable, match="unable to resolve target domain"
        ):
            await bridge.navigate_to_url("http://")

    @pytest.mark.asyncio
    async def test_rejects_non_dict_response(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._capabilities = {"navigate_url"}
        bridge._authorized_domains = ["example.com"]
        bridge._send_request = AsyncMock(return_value="bad")

        with pytest.raises(
            ExtensionBridgeNotAvailable, match="invalid navigate_url response"
        ):
            await bridge.navigate_to_url("https://example.com/page")

    @pytest.mark.asyncio
    async def test_rejects_missing_tab_id(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._capabilities = {"navigate_url"}
        bridge._authorized_domains = ["example.com"]
        bridge._send_request = AsyncMock(
            return_value={"url": "https://example.com/page"}
        )

        with pytest.raises(ExtensionBridgeNotAvailable, match="did not return tab ID"):
            await bridge.navigate_to_url("https://example.com/page")


class TestRefreshTabsSuccess:
    """Cover _refresh_tabs happy path used by list_tabs."""

    @pytest.mark.asyncio
    async def test_refresh_tabs_updates_cached_tabs(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._capabilities = {"list_tabs"}
        bridge._authorized_domains = ["github.com"]
        bridge._send_request = AsyncMock(
            return_value=[
                {
                    "id": 9,
                    "url": "https://github.com/repo",
                    "title": "Repo",
                    "domain": "github.com",
                    "active": True,
                }
            ]
        )

        tabs = await bridge.list_tabs()

        assert len(tabs) == 1
        assert tabs[0].tab_id == 9


class TestConnectWithoutCdpEndpoint:
    """Cover connect() failure when local CDP endpoint is unavailable."""

    @pytest.mark.asyncio
    async def test_connect_raises_when_cdp_missing(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._capabilities = {"attach_debugger"}

        mock_pw = MagicMock()
        bridge._playwright = mock_pw

        with (
            patch.object(
                bridge,
                "_request_debugger_attach",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch.object(bridge, "_resolve_cdp_endpoint", return_value=None),
        ):
            with pytest.raises(
                ExtensionBridgeNotAvailable,
                match="does not expose a direct CDP endpoint",
            ):
                await bridge.connect()


class TestRequestDebuggerAttachErrors:
    """Cover attach_debugger malformed responses."""

    @pytest.mark.asyncio
    async def test_invalid_attach_response_type(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._hello_received = True
        bridge._capabilities = {"attach_debugger"}
        bridge._ws = MagicMock()
        bridge._send_request = AsyncMock(return_value="nope")

        with pytest.raises(
            ExtensionBridgeNotAvailable, match="invalid attach_debugger response"
        ):
            await bridge._request_debugger_attach(domain="example.com")


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
                with patch(
                    "app.services.extension.bridge._broadcast_extension_status"
                ) as mock_broadcast:
                    await bridge.handle_ws_connection(mock_ws)

        assert bridge._connected is False
        assert bridge._ws is None
        assert mock_broadcast.call_args_list[0].args[0] is True
        assert mock_broadcast.call_args_list[-1].args[0] is False


class TestDisconnectPlaywrightCleanup:
    """Cover disconnect() playwright shutdown branches."""

    @pytest.mark.asyncio
    async def test_disconnect_stops_playwright_even_when_close_fails(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        mock_ws = MagicMock()
        mock_ws.client_state = WebSocketState.CONNECTED
        mock_ws.close = AsyncMock(side_effect=RuntimeError("close failed"))
        bridge._ws = mock_ws

        mock_pw = MagicMock()
        mock_pw.stop = AsyncMock()
        bridge._playwright = mock_pw

        await bridge.disconnect()

        mock_pw.stop.assert_awaited_once()
        assert bridge._playwright is None

    @pytest.mark.asyncio
    async def test_disconnect_swallows_playwright_stop_errors(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._ws.client_state = WebSocketState.DISCONNECTED

        mock_pw = MagicMock()
        mock_pw.stop = AsyncMock(side_effect=RuntimeError("stop failed"))
        bridge._playwright = mock_pw

        await bridge.disconnect()

        assert bridge._playwright is None


class TestResolveCdpEndpoint:
    """Cover CDP endpoint discovery helpers."""

    def test_resolve_cdp_endpoint_caches_discovered_value(self) -> None:
        bridge = ExtensionBridgeService()
        with patch(
            "myrm_agent_harness.toolkits.browser.pool.chrome_discovery.discover_chrome_cdp_endpoint",
            return_value="ws://127.0.0.1:9222/devtools/browser/abc",
        ):
            endpoint = bridge._resolve_cdp_endpoint()

        assert endpoint == "ws://127.0.0.1:9222/devtools/browser/abc"
        assert bridge._cdp_endpoint == endpoint

    def test_has_direct_cdp_endpoint_probes_after_ttl(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._last_cdp_probe_monotonic = 0.0
        with patch.object(
            bridge,
            "_resolve_cdp_endpoint",
            return_value="ws://127.0.0.1:9222/devtools/browser/abc",
        ):
            assert bridge.has_direct_cdp_endpoint(probe_ttl_s=0.0) is True


class TestEnsurePlaywright:
    """Cover Playwright singleton startup."""

    @pytest.mark.asyncio
    async def test_ensure_playwright_starts_once(self) -> None:
        bridge = ExtensionBridgeService()
        mock_pw = MagicMock()
        mock_context = MagicMock()
        mock_context.start = AsyncMock(return_value=mock_pw)

        with patch("patchright.async_api.async_playwright", return_value=mock_context):
            first = await bridge._ensure_playwright()
            second = await bridge._ensure_playwright()

        assert first is mock_pw
        assert second is mock_pw
        mock_context.start.assert_awaited_once()


class TestConnectToDomainWithoutCdp:
    """Cover connect_to_domain() when CDP endpoint is missing."""

    @pytest.mark.asyncio
    async def test_connect_to_domain_raises_when_cdp_missing(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._authorized_domains = ["example.com"]
        bridge._hello_received = True
        bridge._capabilities = {"attach_debugger"}
        bridge._playwright = MagicMock()

        with (
            patch.object(
                bridge,
                "_request_debugger_attach",
                new_callable=AsyncMock,
                return_value=7,
            ),
            patch.object(bridge, "_resolve_cdp_endpoint", return_value=None),
        ):
            with pytest.raises(
                ExtensionBridgeNotAvailable,
                match="does not expose a direct CDP endpoint for domain 'example.com'",
            ):
                await bridge.connect_to_domain("example.com")


class TestRequestDebuggerAttachPayload:
    """Cover attach_debugger payload branches."""

    @pytest.mark.asyncio
    async def test_attach_with_explicit_tab_id(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._hello_received = True
        bridge._capabilities = {"attach_debugger"}
        bridge._ws = MagicMock()
        bridge._send_request = AsyncMock(return_value={"tabId": 55})

        tab_id = await bridge._request_debugger_attach(tab_id=55)

        assert tab_id == 55
        bridge._send_request.assert_awaited_once()
        call_args = bridge._send_request.await_args
        assert call_args is not None
        sent_payload = (
            call_args.args[1]
            if len(call_args.args) > 1
            else call_args.kwargs.get("payload")
        )
        assert sent_payload is not None
        assert sent_payload["tabId"] == 55


class TestRefreshTabsFailureSwallowed:
    """Cover _refresh_tabs exception swallow path."""

    @pytest.mark.asyncio
    async def test_refresh_tabs_keeps_existing_tabs_on_capability_error(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._capabilities = set()
        bridge._tabs = [
            ExtensionTab(
                tab_id=1, url="https://github.com", title="GH", domain="github.com"
            ),
        ]

        await bridge._refresh_tabs()

        assert len(bridge._tabs) == 1


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

        with patch.object(
            bridge, "disconnect", new_callable=AsyncMock
        ) as mock_disconnect:
            with patch.object(bridge, "_receive_loop", new_callable=AsyncMock):
                with patch.object(bridge, "_heartbeat_loop", new_callable=AsyncMock):
                    await bridge.handle_ws_connection(new_ws)

        mock_disconnect.assert_awaited_once()


class TestNavigateNotConnected:
    """Cover navigate_to_url guard when websocket is missing."""

    @pytest.mark.asyncio
    async def test_navigate_requires_active_connection(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = False
        bridge._ws = None
        bridge._authorized_domains = ["example.com"]

        with pytest.raises(ExtensionBridgeNotAvailable, match="not connected"):
            await bridge.navigate_to_url("https://example.com/page")


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

        with patch.object(
            bridge, "_receive_loop", new_callable=AsyncMock, side_effect=raise_cancelled
        ):
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

        with patch(
            "app.services.extension.bridge.asyncio.sleep", side_effect=fake_sleep
        ):
            await bridge._heartbeat_loop()

        mock_ws.send_text.assert_awaited_once()
