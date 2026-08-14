"""Coverage-completion tests for ExtensionBridgeService edge branches.

These tests drive the defensive/fallback branches of app.services.extension.bridge
that the main API tests do not reach (heartbeat timeout, relay message dispatch,
import fallback, policy payload application, focus helpers, etc.).
"""

from __future__ import annotations

import json
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.browser.pool.extension_bridge import (
    ExtensionBridgeNotAvailable,
    ExtensionTab,
)
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.services.extension.bridge import ExtensionBridgeService


class FakeWs:
    """Minimal WebSocket stand-in: queues inbound frames, records outbound."""

    client_state = WebSocketState.CONNECTED

    def __init__(self, messages: list[str]) -> None:
        self.messages = list(messages)
        self.sent: list[str] = []

    async def receive_text(self) -> str:
        if not self.messages:
            raise WebSocketDisconnect()
        return self.messages.pop(0)

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def close(self) -> None:
        self.client_state = WebSocketState.DISCONNECTED


class SendFailWs(FakeWs):
    async def send_text(self, text: str) -> None:
        raise OSError("socket closed")


def _authorized_example_tab(active: bool = True) -> ExtensionTab:
    return ExtensionTab(
        tab_id=1,
        url="https://example.com/",
        title="Example",
        domain="example.com",
        active=active,
    )


@pytest.mark.asyncio
async def test_get_status_paused_tab_still_visible_in_ui() -> None:
    bridge = ExtensionBridgeService()
    bridge._tabs = [_authorized_example_tab()]
    await bridge.set_access_policy(
        authorized_domains=["example.com"], paused_tab_ids=[1]
    )
    status = await bridge.get_status()
    assert [t.tab_id for t in status.available_tabs] == [1]


@pytest.mark.asyncio
async def test_relay_cdp_ready_policy_invalid() -> None:
    bridge = ExtensionBridgeService()
    assert await bridge.relay_cdp_ready() is False


@pytest.mark.asyncio
async def test_relay_cdp_ready_connected_binds_transport() -> None:
    bridge = ExtensionBridgeService()
    bridge._connected = True
    bridge._ws = MagicMock()
    await bridge.set_authorized_domains(["example.com"])
    with patch(
        "app.services.extension.bridge.get_cdp_relay_manager"
    ) as mock_manager:
        mock_relay = AsyncMock()
        mock_relay.relay_cdp_ready.return_value = True
        mock_manager.return_value = mock_relay
        assert await bridge.relay_cdp_ready() is True
        mock_relay.bind_extension_transport.assert_called_once()


@pytest.mark.asyncio
async def test_connect_handshake_not_complete_raises() -> None:
    bridge = ExtensionBridgeService()
    bridge._connected = True
    bridge._ws = MagicMock()
    with pytest.raises(ExtensionBridgeNotAvailable, match="handshake"):
        await bridge.connect()


@pytest.mark.asyncio
async def test_connect_policy_invalid_raises() -> None:
    bridge = ExtensionBridgeService()
    bridge._connected = True
    bridge._ws = MagicMock()
    bridge._hello_received = True
    with pytest.raises(ExtensionBridgeNotAvailable, match="access policy"):
        await bridge.connect()


@pytest.mark.asyncio
async def test_connect_success_focuses_preferred_tab() -> None:
    bridge = ExtensionBridgeService()
    bridge._connected = True
    bridge._ws = MagicMock()
    bridge._hello_received = True
    await bridge.set_authorized_domains(["example.com"])
    bridge._tabs = [_authorized_example_tab()]

    mock_browser = MagicMock()
    mock_browser.contexts = []
    mock_pw = MagicMock()
    mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
    with (
        patch.object(
            bridge,
            "_resolve_playwright_cdp_endpoint",
            AsyncMock(return_value="ws://cdp"),
        ),
        patch.object(bridge, "_ensure_playwright", AsyncMock(return_value=mock_pw)),
        patch("app.services.extension.bridge.get_cdp_relay_manager") as mock_manager,
    ):
        mock_manager.return_value = AsyncMock()
        instance = await bridge.connect()

    assert instance.is_managed is False
    assert instance.engine == "chromium-patchright"


@pytest.mark.asyncio
async def test_connect_to_domain_empty_domain_raises() -> None:
    bridge = ExtensionBridgeService()
    with pytest.raises(ExtensionBridgeNotAvailable, match="must not be empty"):
        await bridge.connect_to_domain("  ")


@pytest.mark.asyncio
async def test_connect_to_domain_allow_all_disallows_target() -> None:
    bridge = ExtensionBridgeService()
    await bridge.set_access_policy(
        allow_all_eligible_tabs=True, authorized_domains=["example.com"]
    )
    # ":" yields an https URL with no hostname, which is never an eligible target.
    with pytest.raises(ExtensionBridgeNotAvailable, match="not an eligible"):
        await bridge.connect_to_domain(":")


@pytest.mark.asyncio
async def test_connect_to_domain_handshake_not_complete_raises() -> None:
    bridge = ExtensionBridgeService()
    bridge._connected = True
    bridge._ws = MagicMock()
    await bridge.set_authorized_domains(["example.com"])
    with pytest.raises(ExtensionBridgeNotAvailable, match="handshake"):
        await bridge.connect_to_domain("example.com")


@pytest.mark.asyncio
async def test_connect_to_domain_navigates_then_finds_tab() -> None:
    bridge = ExtensionBridgeService()
    bridge._connected = True
    bridge._ws = MagicMock()
    bridge._hello_received = True
    await bridge.set_access_policy(allow_all_eligible_tabs=True)

    async def fake_send(action: str, payload: dict | None = None, **kwargs: object) -> object:
        if action == "list_tabs":
            return [
                {
                    "id": 7,
                    "url": "https://example.com/path",
                    "title": "Example",
                    "domain": "example.com",
                    "active": True,
                }
            ]
        if action == "navigate_url":
            return {
                "tabId": 7,
                "url": "https://example.com/",
                "title": "Example",
                "domain": "example.com",
                "active": True,
            }
        if action == "attach_debugger":
            return {"tabId": 7}
        return {}

    mock_browser = MagicMock()
    mock_browser.contexts = []
    mock_pw = MagicMock()
    mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
    with (
        patch.object(bridge, "_send_request", side_effect=fake_send),
        patch.object(bridge, "_ensure_playwright", AsyncMock(return_value=mock_pw)),
        patch("app.services.extension.bridge.get_cdp_relay_manager") as mock_manager,
    ):
        mock_manager.return_value = AsyncMock()
        instance = await bridge.connect_to_domain("example.com")

    assert instance.is_managed is False


@pytest.mark.asyncio
async def test_connect_to_domain_no_tab_available_raises() -> None:
    bridge = ExtensionBridgeService()
    bridge._connected = True
    bridge._ws = MagicMock()
    bridge._hello_received = True
    await bridge.set_authorized_domains(["example.com"])
    bridge._tabs = []

    async def fake_send(action: str, payload: dict | None = None, **kwargs: object) -> object:
        if action == "list_tabs":
            return {"not": "a list"}
        if action == "navigate_url":
            return {"tabId": 1, "url": "https://example.com/"}
        return {}

    with (
        patch.object(bridge, "_send_request", side_effect=fake_send),
        patch.object(bridge, "_ensure_playwright", AsyncMock(return_value=MagicMock())),
        patch("app.services.extension.bridge.get_cdp_relay_manager") as mock_manager,
    ):
        mock_manager.return_value = AsyncMock()
        with pytest.raises(ExtensionBridgeNotAvailable, match="No extension tab"):
            await bridge.connect_to_domain("example.com")


@pytest.mark.asyncio
async def test_receive_loop_dispatch_messages() -> None:
    bridge = ExtensionBridgeService()
    bridge._connected = True
    bridge._ws = FakeWs(
        [
            json.dumps({"type": "pong"}),
            json.dumps({"type": "relay_result", "seq": 1, "result": {"ok": True}}),
            json.dumps({"type": "relay_error", "seq": 2, "message": "boom"}),
            json.dumps(
                {
                    "type": "tabs_update",
                    "tabs": [
                        {
                            "id": 1,
                            "url": "https://example.com/",
                            "title": "Example",
                            "domain": "example.com",
                            "active": True,
                        }
                    ],
                }
            ),
            json.dumps({"type": "domains_update", "domains": ["github.com"]}),
            json.dumps(
                {
                    "type": "access_policy_update",
                    "allow_all_eligible_tabs": True,
                    "paused_tab_ids": [1, "2", "abc"],
                }
            ),
            json.dumps({"type": "response", "id": "req_9", "data": {"ok": 1}}),
            json.dumps({"type": "response", "id": "req_missing", "error": "nope"}),
            json.dumps(
                {
                    "type": "hello",
                    "version": "1.0",
                    "browser": "chrome",
                    "capabilities": ["navigate_url"],
                    "userAgent": "ua",
                    "browserVersion": "120",
                }
            ),
        ]
    )
    with patch(
        "app.services.extension.bridge.get_cdp_relay_manager"
    ) as mock_manager:
        mock_relay = AsyncMock()
        mock_manager.return_value = mock_relay
        await bridge._receive_loop()

    assert bridge._hello_received is True
    assert bridge._extension_version == "1.0"
    assert bridge._capabilities == {"navigate_url"}
    assert bridge._authorized_domains == ["github.com"]
    assert bridge._allow_all_eligible_tabs is True
    assert bridge._paused_tab_ids == frozenset({1, 2})
    assert bridge._tabs[0].domain == "example.com"
    mock_relay.set_identity.assert_called_once()
    mock_relay.dispatch_extension_message.assert_called()
    mock_relay.sync_tabs_from_extension.assert_called()
    assert any("set_access_policy" in s for s in bridge._ws.sent)


@pytest.mark.asyncio
async def test_receive_loop_tabs_prune_notifies_policy() -> None:
    bridge = ExtensionBridgeService()
    bridge._connected = True
    bridge._ws = FakeWs(
        [
            json.dumps(
                {
                    "type": "tabs_update",
                    "tabs": [
                        {
                            "id": 1,
                            "url": "https://example.com/",
                            "title": "Example",
                            "domain": "example.com",
                            "active": True,
                        }
                    ],
                }
            )
        ]
    )
    bridge._paused_tab_ids = frozenset({1, 99})
    with (
        patch("app.services.extension.bridge.get_cdp_relay_manager") as mock_manager,
        patch("app.services.extension.bridge._broadcast_extension_status"),
    ):
        mock_manager.return_value = MagicMock()
        await bridge._receive_loop()

    assert bridge._paused_tab_ids == frozenset({1})


@pytest.mark.asyncio
async def test_heartbeat_timeout_disconnects() -> None:
    bridge = ExtensionBridgeService()
    bridge._connected = True
    bridge._ws = FakeWs([])
    bridge._last_heartbeat = time.monotonic() - 60.0
    with (
        patch("asyncio.sleep", new=AsyncMock()),
        patch("app.services.extension.bridge.get_cdp_relay_manager") as mock_manager,
        patch("app.services.extension.bridge._broadcast_extension_status") as mock_broadcast,
    ):
        mock_manager.return_value = AsyncMock()
        await bridge._heartbeat_loop()

    assert bridge._connected is False
    mock_broadcast.assert_called_once_with(False)


@pytest.mark.asyncio
async def test_heartbeat_send_failure_breaks_loop() -> None:
    bridge = ExtensionBridgeService()
    bridge._connected = True
    bridge._ws = SendFailWs([])
    bridge._last_heartbeat = time.monotonic()
    with (
        patch("asyncio.sleep", new=AsyncMock()),
        patch("app.services.extension.bridge.get_cdp_relay_manager") as mock_manager,
    ):
        mock_manager.return_value = AsyncMock()
        await bridge._heartbeat_loop()

    assert bridge._connected is True


@pytest.mark.asyncio
async def test_send_ws_message_disconnected_raises() -> None:
    bridge = ExtensionBridgeService()
    with pytest.raises(ExtensionBridgeNotAvailable, match="not connected"):
        await bridge._send_ws_message({"type": "x"})


@pytest.mark.asyncio
async def test_pick_preferred_extension_tab_prioritizes_active() -> None:
    bridge = ExtensionBridgeService()
    await bridge.set_authorized_domains(["example.com"])
    inactive = ExtensionTab(
        tab_id=1,
        url="https://example.com/",
        title="",
        domain="example.com",
        active=False,
    )
    active = ExtensionTab(
        tab_id=2,
        url="https://example.com/",
        title="",
        domain="example.com",
        active=True,
    )
    bridge._tabs = [inactive, active]
    assert bridge._pick_preferred_extension_tab().tab_id == 2

    bridge._tabs = [inactive]
    assert bridge._pick_preferred_extension_tab().tab_id == 1


@pytest.mark.asyncio
async def test_pick_preferred_extension_tab_empty() -> None:
    bridge = ExtensionBridgeService()
    await bridge.set_authorized_domains(["example.com"])
    bridge._tabs = []
    assert bridge._pick_preferred_extension_tab() is None


@pytest.mark.asyncio
async def test_focus_browser_on_domain_matches_page() -> None:
    mock_page = MagicMock()
    mock_page.url = "https://example.com/path"
    mock_page.bring_to_front = AsyncMock()
    mock_context = MagicMock()
    mock_context.pages = [mock_page]
    mock_browser = MagicMock()
    mock_browser.contexts = [mock_context]

    bridge = ExtensionBridgeService()
    await bridge._focus_browser_on_domain(mock_browser, "example.com")
    mock_page.bring_to_front.assert_awaited_once()


@pytest.mark.asyncio
async def test_focus_browser_on_domain_handles_page_errors() -> None:
    bad_page = MagicMock()
    type(bad_page).url = property(lambda self: (_ for _ in ()).throw(RuntimeError("crashed")))
    good_page = MagicMock()
    good_page.url = "https://example.com/"
    good_page.bring_to_front = AsyncMock(side_effect=RuntimeError("focus denied"))
    mock_context = MagicMock()
    mock_context.pages = [bad_page, good_page]
    mock_browser = MagicMock()
    mock_browser.contexts = [mock_context]

    bridge = ExtensionBridgeService()
    await bridge._focus_browser_on_domain(mock_browser, "example.com")
    good_page.bring_to_front.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_access_policy_default() -> None:
    bridge = ExtensionBridgeService()
    policy = bridge.get_access_policy()
    assert policy.allow_all_eligible_tabs is False
    assert policy.authorized_domains == []
    assert policy.paused_tab_ids == frozenset()


@pytest.mark.asyncio
async def test_apply_access_policy_payload_all_fields() -> None:
    bridge = ExtensionBridgeService()
    bridge._apply_access_policy_payload(
        {
            "allow_all_eligible_tabs": True,
            "domains": ["example.com", "github.com"],
            "paused_tab_ids": [1, "2", "abc", "99x"],
        }
    )
    assert bridge._allow_all_eligible_tabs is True
    assert bridge._authorized_domains == ["example.com", "github.com"]
    assert bridge._paused_tab_ids == frozenset({1, 2})


@pytest.mark.asyncio
async def test_set_access_policy_sets_all_fields() -> None:
    bridge = ExtensionBridgeService()
    policy = await bridge.set_access_policy(
        allow_all_eligible_tabs=True,
        authorized_domains=["example.com"],
        paused_tab_ids=[3],
    )
    assert policy.allow_all_eligible_tabs is True
    assert bridge._paused_tab_ids == frozenset({3})
    assert bridge.get_authorized_domains() == ["example.com"]


@pytest.mark.asyncio
async def test_notify_clip_agent_config_send_failure_swallowed() -> None:
    bridge = ExtensionBridgeService()
    bridge._connected = True
    bridge._ws = SendFailWs([])
    await bridge.notify_clip_agent_config("agent-1", "https://ui.example")
    assert bridge._ws.sent == []


@pytest.mark.asyncio
async def test_resolve_cdp_endpoint_returns_cached() -> None:
    bridge = ExtensionBridgeService()
    bridge._cdp_endpoint = "http://127.0.0.1:9222"
    with patch(
        "myrm_agent_harness.toolkits.browser.pool.chrome_discovery.discover_chrome_cdp_endpoint"
    ) as mock_discover:
        assert bridge._resolve_cdp_endpoint() == "http://127.0.0.1:9222"
        mock_discover.assert_not_called()


@pytest.mark.asyncio
async def test_import_fallback_definitions_when_harness_missing() -> None:
    """The module-level ImportError fallback defines working stand-ins.

    Run in a subprocess so the fallback is exercised in a pristine interpreter
    without reloading the module (and perturbing sibling test state).
    """
    import os
    import subprocess
    import textwrap
    from pathlib import Path

    script = textwrap.dedent(
        """
        import builtins
        import sys

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "myrm_agent_harness.toolkits.browser.pool.extension_bridge":
                raise ImportError("simulated missing harness")
            return real_import(name, *args, **kwargs)

        builtins.__import__ = fake_import

        import app.services.extension.bridge as bridge_mod

        assert issubclass(bridge_mod.ExtensionBridgeNotAvailable, Exception)
        assert bridge_mod.ExtensionTab is not None
        assert bridge_mod.ExtensionStatus is not None
        print("FALLBACK_OK")
        """
    )
    env = dict(os.environ)
    server_root = Path(__file__).resolve().parents[3]
    env["PYTHONPATH"] = os.pathsep.join(
        [str(server_root), *filter(None, env.get("PYTHONPATH", "").split(os.pathsep))]
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    assert "FALLBACK_OK" in result.stdout
