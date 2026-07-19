"""Tests for GET /webui/desktop/permissions endpoint.

Covers:
- Success path: returns permission status JSON with all expected fields
- All-granted vs partial-denied scenarios
- Exception handling: returns 500 with error payload
- Temporary probe session is always closed (success and check_permissions error paths)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(webui=True)


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


class TestGetDesktopPermissions:
    """GET /webui/desktop/permissions endpoint."""

    @pytest.mark.asyncio
    async def test_all_granted(self, client: httpx.AsyncClient) -> None:
        mock_session = AsyncMock()
        mock_status = AsyncMock()
        mock_status.accessibility = True
        mock_status.screen_recording = True
        mock_status.all_granted = True
        mock_status.platform = "macos"
        mock_status.settings_deeplinks = {
            "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
            "screen_recording": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
        }
        mock_session.check_permissions = AsyncMock(return_value=mock_status)
        mock_session.close = AsyncMock()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.session.create_computer_session",
            return_value=mock_session,
        ):
            response = await client.get("/webui/desktop/permissions")

        assert response.status_code == 200
        data = response.json()
        assert data["accessibility"] is True
        assert data["screen_recording"] is True
        assert data["all_granted"] is True
        assert data["platform"] == "macos"
        assert "accessibility" in data["settings_deeplinks"]
        assert "screen_recording" in data["settings_deeplinks"]
        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_accessibility_denied(self, client: httpx.AsyncClient) -> None:
        mock_session = AsyncMock()
        mock_status = AsyncMock()
        mock_status.accessibility = False
        mock_status.screen_recording = True
        mock_status.all_granted = False
        mock_status.platform = "macos"
        mock_status.settings_deeplinks = {"accessibility": "url://a", "screen_recording": "url://b"}
        mock_session.check_permissions = AsyncMock(return_value=mock_status)
        mock_session.close = AsyncMock()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.session.create_computer_session",
            return_value=mock_session,
        ):
            response = await client.get("/webui/desktop/permissions")

        assert response.status_code == 200
        data = response.json()
        assert data["accessibility"] is False
        assert data["screen_recording"] is True
        assert data["all_granted"] is False
        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_screen_recording_denied(self, client: httpx.AsyncClient) -> None:
        mock_session = AsyncMock()
        mock_status = AsyncMock()
        mock_status.accessibility = True
        mock_status.screen_recording = False
        mock_status.all_granted = False
        mock_status.platform = "macos"
        mock_status.settings_deeplinks = {"accessibility": "url://a", "screen_recording": "url://b"}
        mock_session.check_permissions = AsyncMock(return_value=mock_status)
        mock_session.close = AsyncMock()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.session.create_computer_session",
            return_value=mock_session,
        ):
            response = await client.get("/webui/desktop/permissions")

        assert response.status_code == 200
        data = response.json()
        assert data["accessibility"] is True
        assert data["screen_recording"] is False
        assert data["all_granted"] is False
        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_harness_exception_returns_500(self, client: httpx.AsyncClient) -> None:
        with patch(
            "myrm_agent_harness.toolkits.computer_use.session.create_computer_session",
            side_effect=RuntimeError("harness import failed"),
        ):
            response = await client.get("/webui/desktop/permissions")

        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "permissions_check_failed"
        assert "harness import failed" in data["message"]

    @pytest.mark.asyncio
    async def test_check_permissions_raises_returns_500(self, client: httpx.AsyncClient) -> None:
        mock_session = AsyncMock()
        mock_session.check_permissions = AsyncMock(side_effect=OSError("AX probe crash"))
        mock_session.close = AsyncMock()

        with patch(
            "myrm_agent_harness.toolkits.computer_use.session.create_computer_session",
            return_value=mock_session,
        ):
            response = await client.get("/webui/desktop/permissions")

        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "permissions_check_failed"
        assert "AX probe crash" in data["message"]
        mock_session.close.assert_awaited_once()
