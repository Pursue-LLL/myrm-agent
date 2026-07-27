"""Unit tests for Browser Extension Bridge API and service."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.browser.pool.extension_bridge import (
    ExtensionBridgeNotAvailable,
    ExtensionTab,
)
from pydantic import SecretStr
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


class TestSSEBroadcast:
    """Test _broadcast_extension_status SSE integration."""

    @pytest.mark.asyncio
    async def test_disconnect_broadcasts_false(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._ws.client_state = WebSocketState.DISCONNECTED
        bridge._tabs = []

        with patch("app.services.extension.bridge._broadcast_extension_status") as mock_broadcast:
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
        assert ExtensionBridgeService._match_domain("github.com", ["github.com"]) is True

    def test_exact_no_match(self) -> None:
        assert ExtensionBridgeService._match_domain("evil.com", ["github.com"]) is False

    def test_wildcard_subdomain_match(self) -> None:
        assert ExtensionBridgeService._match_domain("mail.google.com", ["*.google.com"]) is True

    def test_wildcard_deep_subdomain(self) -> None:
        assert ExtensionBridgeService._match_domain("a.b.google.com", ["*.google.com"]) is True

    def test_wildcard_matches_root(self) -> None:
        assert ExtensionBridgeService._match_domain("google.com", ["*.google.com"]) is True

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

    def test_wildcard_warning_for_implicit_root(self) -> None:
        warnings = ExtensionBridgeService.analyze_domain_policy_warnings(["*.google.com"])
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
        bridge._cdp_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"

        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
        bridge._playwright = mock_pw

        with patch.object(bridge, "_request_debugger_attach", new_callable=AsyncMock) as mock_attach:
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

        with patch.object(bridge, "_request_debugger_attach", new_callable=AsyncMock) as mock_attach:
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


class TestRequestDebuggerAttach:
    """Test _request_debugger_attach helper."""

    @pytest.mark.asyncio
    async def test_returns_tab_id(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        bridge._ws = mock_ws

        async def set_result_later():
            await asyncio.sleep(0.01)
            req_id = list(bridge._pending_requests.keys())[0]
            bridge._pending_requests[req_id].set_result({"tabId": 42})

        task = asyncio.create_task(set_result_later())
        tab_id = await bridge._request_debugger_attach(domain="example.com", timeout=2.0)
        await task

        assert tab_id == 42

    @pytest.mark.asyncio
    async def test_raises_if_no_tab_id_in_response(self) -> None:
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
        with pytest.raises(ExtensionBridgeNotAvailable, match="did not return attached tab ID"):
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
            patch("app.config.settings.settings.extension_auth_token", new=SecretStr("")),
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
            patch("app.config.settings.settings.extension_auth_token", new=SecretStr("")),
            patch("app.api.extension.router.get_extension_bridge", return_value=bridge),
        ):
            await extension_ws(websocket, token="")

        bridge.handle_ws_connection.assert_awaited_once_with(websocket)
        websocket.close.assert_not_awaited()


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
            patch("app.config.settings.settings.extension_auth_token", new=SecretStr("")),
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
            patch("app.config.settings.settings.extension_auth_token", new=SecretStr("abc")),
        ):
            hints = await get_extension_setup_hints()

        assert hints.auth_token_configured is True
        assert hints.auth_token_required is False
        assert hints.cdp_endpoint_discovered is True

    @pytest.mark.asyncio
    async def test_update_domains_returns_policy_warning(self) -> None:
        from app.api.extension.router import DomainsUpdateRequest, update_authorized_domains

        bridge = MagicMock()
        bridge.set_authorized_domains = AsyncMock()
        bridge.get_authorized_domains.return_value = ["*.example.com"]
        bridge.analyze_domain_policy_warnings.return_value = (
            ExtensionBridgeService.analyze_domain_policy_warnings(["*.example.com"])
        )

        with patch("app.api.extension.router.get_extension_bridge", return_value=bridge):
            response = await update_authorized_domains(
                DomainsUpdateRequest(domains=["*.example.com"])
            )

        assert response.authorized_domains == ["*.example.com"]
        assert len(response.warnings) == 1
        assert response.warnings[0].code == "wildcard_includes_root"
        assert response.warnings[0].root_domain == "example.com"
