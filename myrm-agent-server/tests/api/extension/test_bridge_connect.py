"""Connecting ExtensionBridgeService to the browser through the CDP relay: endpoint discovery, Playwright lifetime, fail-closed rules."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.browser.pool.extension_bridge import (
    ExtensionBridgeNotAvailable,
)
from starlette.websockets import WebSocketState

from app.services.extension.bridge import ExtensionBridgeService
from app.services.extension.bridge.common import RELAY_CAPABILITY


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


class TestDirectCdpRiskGovernance:
    """Test explicit direct CDP risk warning emission."""

    @pytest.mark.asyncio
    async def test_connect_uses_relay_endpoint(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._capabilities = {RELAY_CAPABILITY}
        bridge._authorized_domains = ["example.com"]

        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
        bridge._playwright = mock_pw

        with (
            patch.object(bridge, "_sync_relay_tabs", new_callable=AsyncMock),
            patch("app.services.extension.bridge.common.get_cdp_relay_manager") as mock_manager_factory,
        ):
            manager = MagicMock()
            manager.relay_cdp_ready = AsyncMock(return_value=True)
            manager.ensure_http_endpoint = AsyncMock(return_value="http://127.0.0.1:9222")
            manager.bind_extension_transport = AsyncMock()
            mock_manager_factory.return_value = manager

            instance = await bridge.connect()

        mock_pw.chromium.connect_over_cdp.assert_awaited_once_with("http://127.0.0.1:9222", timeout=10000)
        assert instance.browser is mock_browser


class TestConnectWithoutCdpEndpoint:
    """Cover connect() failure when CDP relay is unavailable."""

    @pytest.mark.asyncio
    async def test_connect_raises_when_relay_missing(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._capabilities = {RELAY_CAPABILITY}
        bridge._authorized_domains = ["example.com"]

        with (
            patch.object(bridge, "_sync_relay_tabs", new_callable=AsyncMock),
            patch("app.services.extension.bridge.common.get_cdp_relay_manager") as mock_manager_factory,
        ):
            manager = MagicMock()
            manager.relay_cdp_ready = AsyncMock(return_value=False)
            manager.bind_extension_transport = AsyncMock()
            mock_manager_factory.return_value = manager
            with patch.object(bridge, "_resolve_cdp_endpoint", return_value=None):
                with pytest.raises(
                    ExtensionBridgeNotAvailable,
                    match="CDP relay is not ready",
                ):
                    await bridge.connect()

    @pytest.mark.asyncio
    async def test_connect_rejects_direct_cdp_fallback_when_relay_missing(self) -> None:
        """Extension mode must not bypass policy via local :9222 discovery."""
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._capabilities = {RELAY_CAPABILITY}
        bridge._authorized_domains = ["example.com"]

        with (
            patch.object(bridge, "_sync_relay_tabs", new_callable=AsyncMock),
            patch("app.services.extension.bridge.common.get_cdp_relay_manager") as mock_manager_factory,
        ):
            manager = MagicMock()
            manager.relay_cdp_ready = AsyncMock(return_value=False)
            manager.bind_extension_transport = AsyncMock()
            mock_manager_factory.return_value = manager
            with patch.object(
                bridge,
                "_resolve_cdp_endpoint",
                return_value="http://127.0.0.1:9222",
            ) as mock_resolve:
                with pytest.raises(
                    ExtensionBridgeNotAvailable,
                    match="CDP relay is not ready",
                ):
                    await bridge.connect()
                mock_resolve.assert_not_called()


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
