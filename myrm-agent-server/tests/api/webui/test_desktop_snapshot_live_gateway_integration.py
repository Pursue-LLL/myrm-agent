"""Live gateway + DesktopSession integration for GET /webui/desktop/snapshot (no AX mock).

Uses real macOS AX + SOM overlay via export_inspector_snapshot. Injects an active
desktop session into AgentGateway (same guard the router uses in production).
"""

from __future__ import annotations

import platform
import subprocess
import time
import weakref
from collections.abc import AsyncGenerator

import httpx
import pytest
from httpx import ASGITransport
from myrm_agent_harness.toolkits.computer_use.backends.macos import _check_accessibility
from myrm_agent_harness.toolkits.computer_use.desktop_session import create_desktop_session

from app.services.agent.gateway import ActiveSessionInfo, AgentGateway, GatewayConfig
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(webui=True)

_INTERACTIVE_ROLES = frozenset(
    {"button", "textbox", "checkbox", "link", "menuitem", "tab", "combobox"}
)


def _activate_foreground_app() -> None:
    if platform.system() != "Darwin":
        return
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "TextEdit" to activate',
            "-e",
            'tell application "TextEdit" to make new document',
            "-e",
            'tell application "System Events" to tell process "TextEdit" to set frontmost to true',
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    time.sleep(2.0)


_PREFLIGHT_AX_COUNT_SCRIPT = """
tell application "System Events"
    try
        set frontApp to first application process whose frontmost is true
        return count (entire contents of window 1 of frontApp)
    on error
        return -1
    end try
end tell
"""


def _preflight_ax_elements() -> int:
    """Return UI element count for frontmost window, or -1 when AX is unavailable."""
    if not _check_accessibility():
        return -1
    result = subprocess.run(
        ["osascript", "-e", _PREFLIGHT_AX_COUNT_SCRIPT],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return -1
    try:
        return int(result.stdout.strip())
    except ValueError:
        return -1


def _gateway_with_live_session() -> tuple[AgentGateway, object]:
    session = create_desktop_session()
    gateway = AgentGateway(GatewayConfig(max_global=4, max_per_user=2, queue_timeout=30.0, execution_timeout=300.0))

    class _AgentWithDesktop:
        def __init__(self) -> None:
            self._desktop_session = session

    agent = _AgentWithDesktop()
    info = ActiveSessionInfo(chat_id="live-som-gateway", agent_type="general")
    info.agent = weakref.ref(agent)
    gateway._session_info["live-som-gateway"] = info
    gateway._test_agent_holder = agent  # strong ref: weakref alone is GC'd after setup
    return gateway, session


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


@pytest.mark.integration
@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS AX only")
@pytest.mark.asyncio
async def test_live_gateway_desktop_snapshot_api_returns_som_nth(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full API path with live AX: gateway → DesktopSession.export_inspector_snapshot → nth."""
    _activate_foreground_app()
    element_count = _preflight_ax_elements()
    if element_count < 0:
        pytest.skip(
            "osascript cannot enumerate AX tree (grant Accessibility to Terminal/Cursor)"
        )
    if element_count == 0:
        pytest.skip(
            "foreground app has no AX elements in this environment; "
            "use test_desktop_snapshot_gateway_integration for deterministic SOM nth"
        )

    gateway, session = _gateway_with_live_session()
    monkeypatch.setattr("app.services.agent.gateway.get_agent_gateway", lambda: gateway)
    try:
        response = await client.get("/webui/desktop/snapshot")
    finally:
        await session.close()
        gateway._session_info.pop("live-som-gateway", None)

    if response.status_code == 500:
        body = response.json()
        message = str(body.get("message", ""))
        if "empty" in message.lower() or "permission" in message.lower():
            pytest.fail(
                f"Live AX capture failed: {message}. "
                "Grant Accessibility + Screen Recording and foreground TextEdit."
            )
        pytest.fail(f"Unexpected snapshot failure: {response.text}")

    assert response.status_code == 200, response.text
    data = response.json()
    if data.get("needs_permission"):
        pytest.fail("macOS Accessibility or Screen Recording permission missing")

    refs = data.get("refs")
    assert isinstance(refs, dict), data
    if not refs:
        pytest.fail(
            f"Accessibility tree empty (app={data.get('app_name')!r}). "
            "Foreground a native app with interactive controls."
        )

    interactive = [
        ref for ref in refs.values() if isinstance(ref, dict) and ref.get("role") in _INTERACTIVE_ROLES
    ]
    if not interactive:
        pytest.fail(f"No interactive refs among {len(refs)} nodes (app={data.get('app_name')!r})")

    missing_nth = [ref.get("role") for ref in interactive if ref.get("nth") is None]
    assert not missing_nth, f"interactive refs missing nth: {missing_nth[:8]}"
    assert data.get("screenshot_base64"), "expected SOM-annotated screenshot"
