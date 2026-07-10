"""Gateway + DesktopSession integration for GET /webui/desktop/snapshot.

Mocks only AX capture and screenshot I/O (OS boundary). SOM overlay, nth fill,
and router isinstance guard run through real DesktopSession.export_inspector_snapshot.
"""

from __future__ import annotations

import base64
import io
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport
from PIL import Image

from myrm_agent_harness.toolkits.computer_use.coordinate_scaler import CoordinateScaler
from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef, SnapshotMeta
from myrm_agent_harness.toolkits.computer_use.types import ActionResult, ComputerUseConfig, ScreenInfo
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(webui=True)


def _jpeg_base64(width: int = 400, height: int = 300) -> str:
    image = Image.new("RGB", (width, height), color=(210, 210, 210))
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def _real_desktop_session() -> DesktopSession:
    backend = MagicMock()
    backend.screen_info.return_value = ScreenInfo(width=800, height=600, dpi_scale=1.0)
    session = DesktopSession(backend=backend, config=ComputerUseConfig())
    session._scaler = CoordinateScaler(
        screen_width=800,
        screen_height=600,
        sent_width=400,
        sent_height=300,
        dpi_scale=1.0,
    )
    return session


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
    meta = SnapshotMeta(
        ref_count=2,
        app_name="TextEdit",
        window_title="Untitled",
        scope="foreground",
    )
    refs = {
        "d1": ElementRef(
            ref_id="d1",
            role="AXButton",
            name="OK",
            bbox=BBox(50, 50, 80, 40),
            backend_key="k1",
        ),
        "d2": ElementRef(
            ref_id="d2",
            role="AXStaticText",
            name="Label",
            bbox=BBox(10, 10, 40, 20),
            backend_key="k2",
        ),
    }
    original_b64 = _jpeg_base64()
    session = _real_desktop_session()
    session.take_screenshot = AsyncMock(  # type: ignore[method-assign]
        return_value=ActionResult(
            success=True,
            screenshot_base64=original_b64,
            screenshot_size=(400, 300),
        )
    )

    mock_gateway = MagicMock()
    mock_gateway.get_active_desktop_session.return_value = session

    with (
        patch("app.services.agent.gateway.get_agent_gateway", return_value=mock_gateway),
        patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.capture_snapshot",
            return_value=(meta, refs),
        ),
    ):
        response = await client.get("/webui/desktop/snapshot")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["app_name"] == "TextEdit"
    assert data["refs"]["d1"]["nth"] == 1
    assert data["refs"]["d2"].get("nth") is None
    assert data["screenshot_base64"]
    assert data["screenshot_base64"] != original_b64
    assert data["mime_type"] == "image/jpeg"
