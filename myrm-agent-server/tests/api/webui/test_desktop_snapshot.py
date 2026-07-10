"""Tests for GET /webui/desktop/snapshot endpoint (Desktop Inspector)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport

from tests.support.minimal_app import build_minimal_app

from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.types import ComputerUseConfig, ScreenInfo

app = build_minimal_app(webui=True)


def _desktop_session_with_export(return_value: object | Exception) -> DesktopSession:
    backend = MagicMock()
    backend.screen_info.return_value = ScreenInfo(width=800, height=600, dpi_scale=1.0)
    session = DesktopSession(backend=backend, config=ComputerUseConfig())
    if isinstance(return_value, Exception):
        session.export_inspector_snapshot = AsyncMock(side_effect=return_value)  # type: ignore[method-assign]
    else:
        session.export_inspector_snapshot = AsyncMock(return_value=return_value)  # type: ignore[method-assign]
    return session


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


class TestGetDesktopSnapshot:
    @pytest.mark.asyncio
    async def test_no_active_session_returns_404(self, client: httpx.AsyncClient) -> None:
        mock_gateway = MagicMock()
        mock_gateway.get_active_desktop_session.return_value = None

        with patch("app.services.agent.gateway.get_agent_gateway", return_value=mock_gateway):
            response = await client.get("/webui/desktop/snapshot")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "no_active_desktop"

    @pytest.mark.asyncio
    async def test_returns_snapshot_with_som_nth(self, client: httpx.AsyncClient) -> None:
        payload = {
            "screenshot_base64": "img",
            "mime_type": "image/jpeg",
            "refs": {
                "d1": {
                    "role": "button",
                    "name": "OK",
                    "nth": 1,
                    "bbox": {
                        "x": 10,
                        "y": 10,
                        "width": 40,
                        "height": 30,
                        "centerX": 30,
                        "centerY": 25,
                        "viewport_width": 800,
                        "viewport_height": 600,
                    },
                    "position": None,
                }
            },
            "app_name": "App",
            "window_title": "Window",
            "scope": "foreground",
            "needs_permission": False,
            "viewport_width": 800,
            "viewport_height": 600,
            "screen_width": 800,
            "screen_height": 600,
            "dpi_scale": 1.0,
        }
        mock_session = _desktop_session_with_export(payload)

        mock_gateway = MagicMock()
        mock_gateway.get_active_desktop_session.return_value = mock_session

        with patch("app.services.agent.gateway.get_agent_gateway", return_value=mock_gateway):
            response = await client.get("/webui/desktop/snapshot")

        assert response.status_code == 200
        data = response.json()
        assert data["refs"]["d1"]["nth"] == 1
        assert data["mime_type"] == "image/jpeg"

    @pytest.mark.asyncio
    async def test_invalid_session_type_returns_404(self, client: httpx.AsyncClient) -> None:
        mock_gateway = MagicMock()
        mock_gateway.get_active_desktop_session.return_value = object()

        with patch("app.services.agent.gateway.get_agent_gateway", return_value=mock_gateway):
            response = await client.get("/webui/desktop/snapshot")

        assert response.status_code == 404
        assert response.json()["error"] == "invalid_session"

    @pytest.mark.asyncio
    async def test_export_failure_returns_500(self, client: httpx.AsyncClient) -> None:
        mock_session = _desktop_session_with_export(RuntimeError("capture failed"))

        mock_gateway = MagicMock()
        mock_gateway.get_active_desktop_session.return_value = mock_session

        with patch("app.services.agent.gateway.get_agent_gateway", return_value=mock_gateway):
            response = await client.get("/webui/desktop/snapshot")

        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "snapshot_failed"
        assert "capture failed" in data["message"]
