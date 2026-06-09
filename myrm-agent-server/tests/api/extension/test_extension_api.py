"""Unit tests for Browser Extension Bridge API and service."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

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
        from myrm_agent_harness.toolkits.browser.pool.extension_bridge import ExtensionBridgeNotAvailable

        bridge = ExtensionBridgeService()
        with pytest.raises(ExtensionBridgeNotAvailable, match="not connected"):
            await bridge.connect()

    @pytest.mark.asyncio
    async def test_connect_to_unauthorized_domain_raises(self) -> None:
        from myrm_agent_harness.toolkits.browser.pool.extension_bridge import ExtensionBridgeNotAvailable

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


class TestExtensionBridgeSingleton:
    """Test singleton access."""

    def test_get_extension_bridge_returns_same_instance(self) -> None:
        bridge1 = get_extension_bridge()
        bridge2 = get_extension_bridge()
        assert bridge1 is bridge2
