"""Requests ExtensionBridgeService sends to the extension: navigation, capability gating, request bookkeeping."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.toolkits.browser.pool.extension_bridge import (
    ExtensionBridgeNotAvailable,
)

from app.services.extension.bridge import ExtensionBridgeService


class TestNavigateToUrl:
    """Test navigate_to_url extension flow (no direct CDP requirement)."""

    @pytest.mark.asyncio
    async def test_navigate_to_url_success(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._authorized_domains = ["example.com"]
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
        bridge._authorized_domains = ["example.com"]
        bridge._capabilities = set()
        bridge._authorized_domains = ["*.corp.local"]

        with pytest.raises(ExtensionBridgeNotAvailable, match="missing required capability"):
            await bridge.navigate_to_url("http://portal.corp.local/dashboard")

    @pytest.mark.asyncio
    async def test_navigate_to_url_requires_hello_handshake(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = False
        bridge._capabilities = {"navigate_url"}
        bridge._authorized_domains = ["*.corp.local"]

        with pytest.raises(ExtensionBridgeNotAvailable, match="handshake is not completed"):
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

        with pytest.raises(ExtensionBridgeNotAvailable, match="does not match navigation target"):
            await bridge.navigate_to_url(
                "http://portal.corp.local/dashboard",
                domain="evil.local",
            )


class TestNavigateToUrlAdditionalErrors:
    """Cover navigate_to_url validation and malformed extension responses."""

    @pytest.mark.asyncio
    async def test_rejects_url_without_hostname(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._authorized_domains = ["example.com"]

        with pytest.raises(ExtensionBridgeNotAvailable, match="unable to resolve target domain"):
            await bridge.navigate_to_url("http://")

    @pytest.mark.asyncio
    async def test_rejects_non_dict_response(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._authorized_domains = ["example.com"]
        bridge._capabilities = {"navigate_url"}
        bridge._authorized_domains = ["example.com"]
        bridge._send_request = AsyncMock(return_value="bad")

        with pytest.raises(ExtensionBridgeNotAvailable, match="invalid navigate_url response"):
            await bridge.navigate_to_url("https://example.com/page")

    @pytest.mark.asyncio
    async def test_rejects_missing_tab_id(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._authorized_domains = ["example.com"]
        bridge._capabilities = {"navigate_url"}
        bridge._authorized_domains = ["example.com"]
        bridge._send_request = AsyncMock(return_value={"url": "https://example.com/page"})

        with pytest.raises(ExtensionBridgeNotAvailable, match="did not return tab ID"):
            await bridge.navigate_to_url("https://example.com/page")


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


class TestActionCapabilityContract:
    """Test action-level capability enforcement for extension relay actions."""

    @pytest.mark.asyncio
    async def test_send_request_requires_mapped_capability(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._authorized_domains = ["example.com"]
        bridge._capabilities = set()

        with pytest.raises(ExtensionBridgeNotAvailable, match="missing required capability 'list_tabs'"):
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
