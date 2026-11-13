"""The extension bridge's REST and WebSocket router, and the Wiki clip-agent sync."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.browser.pool.extension_bridge import (
    ExtensionTab,
)
from pydantic import SecretStr

from app.services.extension.bridge import ExtensionBridgeService
from app.services.extension.bridge.common import RELAY_CAPABILITY


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

        websocket.close.assert_awaited_once_with(code=4002, reason="Extension auth token required in remote mode")

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
        bridge.analyze_domain_policy_warnings.return_value = ExtensionBridgeService.analyze_domain_policy_warnings(
            ["*.example.com"]
        )

        with patch("app.api.extension.router.get_extension_bridge", return_value=bridge):
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

        with patch("app.api.extension.router.get_extension_bridge", return_value=bridge):
            tabs = await list_extension_tabs()

        assert len(tabs) == 1
        assert tabs[0].tab_id == 3
        assert tabs[0].active is True

    @pytest.mark.asyncio
    async def test_disconnect_extension_calls_bridge(self) -> None:
        from app.api.extension.router import disconnect_extension

        bridge = MagicMock()
        bridge.disconnect = AsyncMock()

        with patch("app.api.extension.router.get_extension_bridge", return_value=bridge):
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
        bridge.relay_cdp_ready = AsyncMock(return_value=False)
        bridge.is_access_policy_valid.return_value = True

        mock_request = MagicMock()

        with (
            patch("app.api.extension.router.get_extension_bridge", return_value=bridge),
            patch("app.config.deploy_mode.is_webui_remote_mode", return_value=True),
            patch("app.config.settings.settings.extension_auth_token", new=SecretStr("")),
        ):
            hints = await get_extension_setup_hints(mock_request)

        assert hints.auth_token_configured is False
        assert hints.auth_token_required is True
        assert hints.cdp_endpoint_discovered is False
        bridge.has_direct_cdp_endpoint.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_setup_hints_local_token_optional(self) -> None:
        from app.api.extension.router import get_extension_setup_hints

        bridge = MagicMock()
        bridge.has_direct_cdp_endpoint.return_value = True
        bridge.relay_cdp_ready = AsyncMock(return_value=True)
        bridge.is_access_policy_valid.return_value = True

        mock_request = MagicMock()

        with (
            patch("app.api.extension.router.get_extension_bridge", return_value=bridge),
            patch("app.config.deploy_mode.is_webui_remote_mode", return_value=False),
            patch(
                "app.config.settings.settings.extension_auth_token",
                new=SecretStr("abc"),
            ),
        ):
            hints = await get_extension_setup_hints(mock_request)

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
        bridge.analyze_domain_policy_warnings.return_value = ExtensionBridgeService.analyze_domain_policy_warnings(
            ["*.example.com"]
        )

        with patch("app.api.extension.router.get_extension_bridge", return_value=bridge):
            response = await update_authorized_domains(DomainsUpdateRequest(domains=["*.example.com"]))

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
                capabilities=["navigate_url", "list_tabs", RELAY_CAPABILITY],
                available_tabs=[],
            )
        )
        bridge.get_access_policy.return_value = SimpleNamespace(
            allow_all_eligible_tabs=False,
            authorized_domains=["corp.local"],
            paused_tab_ids=frozenset(),
        )
        bridge.relay_cdp_ready = AsyncMock(return_value=True)
        bridge.is_access_policy_valid.return_value = True

        with patch("app.api.extension.router.get_extension_bridge", return_value=bridge):
            status = await get_extension_status()

        assert status.connected is True
        assert status.handshake_ready is True
        assert status.capabilities == ["navigate_url", "list_tabs", RELAY_CAPABILITY]


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
