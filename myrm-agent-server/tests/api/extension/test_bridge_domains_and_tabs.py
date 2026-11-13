"""Domain authorization, the tab mirror and policy notification of ExtensionBridgeService."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.browser.pool.extension_bridge import (
    ExtensionBridgeNotAvailable,
    ExtensionTab,
)

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
        warnings = ExtensionBridgeService.analyze_domain_policy_warnings(["*.google.com", "google.com"])
        assert warnings == []


class TestMatchDomainEdgeCases:
    """Cover wildcard and empty-input branches in _match_domain."""

    def test_empty_domain_returns_false(self) -> None:
        assert ExtensionBridgeService._match_domain("", ["example.com"]) is False

    def test_empty_pattern_is_skipped(self) -> None:
        assert ExtensionBridgeService._match_domain("example.com", ["", "example.com"]) is True

    def test_bare_wildcard_pattern_is_skipped(self) -> None:
        assert ExtensionBridgeService._match_domain("example.com", ["*."]) is False


class TestDomainPolicyWarningNormalization:
    """Cover duplicate/empty filtering in analyze_domain_policy_warnings."""

    def test_deduplicates_and_skips_empty_entries(self) -> None:
        warnings = ExtensionBridgeService.analyze_domain_policy_warnings(["", " *.example.com ", "*.example.com", "example.com"])
        assert warnings == []


class TestNormalizeCapabilities:
    """Cover capability normalization used by hello handshake."""

    def test_non_list_payload_returns_empty_set(self) -> None:
        assert ExtensionBridgeService._normalize_capabilities("navigate_url") == set()

    def test_mixed_payload_normalizes_tokens(self) -> None:
        caps = ExtensionBridgeService._normalize_capabilities([" Navigate_URL ", "", 42, "list_tabs"])
        assert caps == {"navigate_url", "list_tabs"}


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
        assert sent["type"] == "set_access_policy"
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


class TestRefreshTabsSuccess:
    """Cover _refresh_tabs happy path used by list_tabs."""

    @pytest.mark.asyncio
    async def test_refresh_tabs_updates_cached_tabs(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._authorized_domains = ["example.com"]
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


class TestRefreshTabsFailureSwallowed:
    """Cover _refresh_tabs exception swallow path."""

    @pytest.mark.asyncio
    async def test_refresh_tabs_keeps_existing_tabs_on_capability_error(self) -> None:
        bridge = ExtensionBridgeService()
        bridge._connected = True
        bridge._ws = MagicMock()
        bridge._hello_received = True
        bridge._authorized_domains = ["example.com"]
        bridge._capabilities = set()
        bridge._tabs = [
            ExtensionTab(tab_id=1, url="https://github.com", title="GH", domain="github.com"),
        ]

        await bridge._refresh_tabs()

        assert len(bridge._tabs) == 1


class TestExtensionBridgeSingleton:
    """Test singleton access."""

    def test_get_extension_bridge_returns_same_instance(self) -> None:
        bridge1 = get_extension_bridge()
        bridge2 = get_extension_bridge()
        assert bridge1 is bridge2
