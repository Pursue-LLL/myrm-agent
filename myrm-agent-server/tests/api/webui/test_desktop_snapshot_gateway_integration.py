"""Gateway + DesktopSession integration for GET /webui/desktop/snapshot.

Mocks only the AX capture and the screen capture (the OS boundary). The overlay numbering, the action lock, the
screen guard, the single registry write entry and the router isinstance guard run through the real DesktopSession.
"""

from __future__ import annotations

import io
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport
from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef, SnapshotMeta
from myrm_agent_harness.toolkits.computer_use.types import ComputerUseConfig, ScreenInfo
from PIL import Image

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(webui=True)

_INSPECTOR_CAPTURE = "myrm_agent_harness.toolkits.computer_use.desktop_session.views.capture_snapshot"
_SCREEN = ScreenInfo(width=800, height=600, dpi_scale=1.0)


def _screen_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (_SCREEN.width, _SCREEN.height), color=(210, 210, 210)).save(buffer, format="PNG")
    return buffer.getvalue()


def _real_desktop_session() -> DesktopSession:
    backend = MagicMock()
    backend.screen_info.return_value = _SCREEN
    backend.screenshot = AsyncMock(return_value=_screen_png())
    return DesktopSession(backend=backend, config=ComputerUseConfig())


def _mail_capture() -> tuple[SnapshotMeta, dict[str, ElementRef]]:
    meta = SnapshotMeta(ref_count=2, app_name="Mail", window_title="Inbox", scope="foreground", pid=100)
    refs = {
        "d0": ElementRef(ref_id="d0", role="AXButton", name="Reply", bbox=BBox(50, 50, 80, 40), backend_key="k1"),
        "d1": ElementRef(ref_id="d1", role="AXStaticText", name="Label", bbox=BBox(10, 10, 40, 20), backend_key="k2"),
    }
    return meta, refs


def _gateway_serving(session: DesktopSession) -> MagicMock:
    gateway = MagicMock()
    gateway.get_active_desktop_session.return_value = session
    return gateway


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


@pytest.mark.integration
@pytest.mark.asyncio
async def test_snapshot_api_real_export_inspector_snapshot_som_nth(
    client: httpx.AsyncClient,
) -> None:
    """Full API path: gateway → DesktopSession → SOM nth in JSON refs."""
    session = _real_desktop_session()
    plain, _ = session._processor.process(_screen_png(), _SCREEN)

    with (
        patch("app.services.agent.gateway.get_agent_gateway", return_value=_gateway_serving(session)),
        patch(_INSPECTOR_CAPTURE, return_value=_mail_capture()),
    ):
        response = await client.get("/webui/desktop/snapshot")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["app_name"] == "Mail"
    assert data["refs"]["d0"]["nth"] == 1
    assert data["refs"]["d1"].get("nth") is None
    assert data["screenshot_base64"] not in ("", plain)
    assert data["mime_type"] == "image/jpeg"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_snapshot_api_registry_source_draws_the_agents_registry_without_reading_the_tree(
    client: httpx.AsyncClient,
) -> None:
    """The automatic refresh: the agent's own elements over the current screen, no AX read, no registry write."""
    session = _real_desktop_session()
    session._adopt_capture(*_mail_capture())
    registered, generation = session.ref_registry.all_refs(), session.ref_registry.generation
    gateway = _gateway_serving(session)

    with (
        patch("app.services.agent.gateway.get_agent_gateway", return_value=gateway),
        patch(_INSPECTOR_CAPTURE, side_effect=AssertionError("the accessibility tree was read")) as capture,
    ):
        response = await client.get("/webui/desktop/snapshot", params={"source": "registry", "chat_id": "chat-1"})

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["screenshot_base64"]
    assert data["refs"]["d0"]["nth"] == 1
    assert data["registry_generation"] == generation
    capture.assert_not_called()
    gateway.get_active_desktop_session.assert_called_once_with("chat-1")
    assert session.ref_registry.all_refs() == registered


@pytest.mark.integration
@pytest.mark.asyncio
async def test_snapshot_api_manual_refresh_of_a_blocked_application_leaves_the_agents_registry_alone(
    client: httpx.AsyncClient,
) -> None:
    """A password manager in front is neither registered nor drawn; the registry view still serves the agent's own."""
    session = _real_desktop_session()
    session._adopt_capture(*_mail_capture())
    registered = session.ref_registry.all_refs()
    vault = SnapshotMeta(ref_count=1, app_name="1Password", window_title="Vault", scope="foreground", pid=200)
    vault_refs = {"d0": ElementRef(ref_id="d0", role="AXTextField", name="Password", bbox=BBox(5, 5, 90, 30), backend_key="v0")}

    with (
        patch("app.services.agent.gateway.get_agent_gateway", return_value=_gateway_serving(session)),
        patch(_INSPECTOR_CAPTURE, return_value=(vault, vault_refs)),
    ):
        live = await client.get("/webui/desktop/snapshot", params={"source": "live", "chat_id": "chat-1"})
        registry = await client.get("/webui/desktop/snapshot", params={"source": "registry", "chat_id": "chat-1"})

    assert live.status_code == 200, live.text
    assert live.json()["refs"] == {}
    assert live.json()["screenshot_base64"] == ""
    assert registry.status_code == 200, registry.text
    assert {ref["name"] for ref in registry.json()["refs"].values()} == {"Reply", "Label"}
    assert session.ref_registry.all_refs() == registered
