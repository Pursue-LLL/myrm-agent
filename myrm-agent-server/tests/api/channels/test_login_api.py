"""Tests for channel login API — SSE event format, on-demand start timeout, cancel flow.

[POS]
Tests for app/api/channels/login.py ensuring correct SSE event format,
on-demand channel start timeout, and session cancellation.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.channels.protocols import LoginMethod, LoginStatus
from app.channels.types import ChannelStatus, StartMode
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="channels_local")
async def _mock_db_gen():
    yield "mock_db"


@pytest.fixture(autouse=True)
def _override_db():
    app.dependency_overrides[get_db_session] = _mock_db_gen
    yield
    app.dependency_overrides.clear()


@asynccontextmanager
async def _noop_lifespan(_app):
    yield


@pytest.fixture
def client():
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.router.lifespan_context = original_lifespan


def _make_mock_channel(
    *,
    start_mode: StartMode = StartMode.ON_DEMAND,
    status: ChannelStatus = ChannelStatus.IDLE,
    supported_methods: list[LoginMethod] | None = None,
) -> MagicMock:
    ch = MagicMock()
    ch.start_mode = start_mode
    ch.status = status
    ch.supported_login_methods = supported_methods or [LoginMethod.QR_CODE]
    ch.start = AsyncMock()
    ch.stop = AsyncMock()
    ch.cancel_login = AsyncMock()
    return ch


class TestStartLogin:
    """Tests for POST /channels/{channel_id}/login/start."""

    def test_start_login_returns_session(self, client):
        mock_ch = _make_mock_channel(status=ChannelStatus.RUNNING)
        with patch("app.api.channels.login.channel_gateway") as gw:
            gw.bus.channels.get.return_value = mock_ch
            resp = client.post(
                "/api/v1/channels/whatsapp/login/start",
                json={"method": "qr_code"},
                headers={"Authorization": "Bearer test"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["channel_id"] == "whatsapp"
        assert data["method"] == "qr_code"
        assert "stream_url" in data

    def test_start_login_channel_not_found(self, client):
        with patch("app.api.channels.login.channel_gateway") as gw:
            gw.bus.channels.get.return_value = None
            resp = client.post(
                "/api/v1/channels/whatsapp/login/start",
                json={"method": "qr_code"},
                headers={"Authorization": "Bearer test"},
            )
        assert resp.status_code == 404

    def test_start_login_on_demand_calls_start(self, client):
        mock_ch = _make_mock_channel(status=ChannelStatus.IDLE)

        async def fake_start():
            mock_ch.status = ChannelStatus.RUNNING

        mock_ch.start = AsyncMock(side_effect=fake_start)

        with patch("app.api.channels.login.channel_gateway") as gw:
            gw.bus.channels.get.return_value = mock_ch
            resp = client.post(
                "/api/v1/channels/whatsapp/login/start",
                json={"method": "qr_code"},
                headers={"Authorization": "Bearer test"},
            )
        assert resp.status_code == 200
        mock_ch.start.assert_called_once()

    def test_start_login_on_demand_timeout(self, client):
        mock_ch = _make_mock_channel(status=ChannelStatus.IDLE)

        async def hang_forever():
            await asyncio.sleep(9999)

        mock_ch.start = AsyncMock(side_effect=hang_forever)

        with (
            patch("app.api.channels.login.channel_gateway") as gw,
            patch("app.api.channels.login._ON_DEMAND_START_TIMEOUT", 0.1),
        ):
            gw.bus.channels.get.return_value = mock_ch
            resp = client.post(
                "/api/v1/channels/whatsapp/login/start",
                json={"method": "qr_code"},
                headers={"Authorization": "Bearer test"},
            )
        assert resp.status_code == 503
        assert "timed out" in resp.json()["detail"]
        mock_ch.stop.assert_called_once()

    def test_start_login_unsupported_method(self, client):
        mock_ch = _make_mock_channel(
            status=ChannelStatus.RUNNING,
            supported_methods=[LoginMethod.QR_CODE],
        )
        with patch("app.api.channels.login.channel_gateway") as gw:
            gw.bus.channels.get.return_value = mock_ch
            resp = client.post(
                "/api/v1/channels/whatsapp/login/start",
                json={"method": "oauth2"},
                headers={"Authorization": "Bearer test"},
            )
        assert resp.status_code == 400
        assert "does not support" in resp.json()["detail"]


class TestSSEStream:
    """Tests for GET /channels/login/{session_id}/stream — event format."""

    def test_sse_has_event_type_prefix(self, client):
        mock_ch = _make_mock_channel(status=ChannelStatus.RUNNING)

        mock_event = MagicMock()
        mock_event.timestamp = 1234567890.0
        mock_event.state.status = LoginStatus.WAITING_USER_ACTION
        mock_event.state.method = LoginMethod.QR_CODE
        mock_event.state.qr_code_base64 = "ABC123"
        mock_event.state.qr_expires_at = None
        mock_event.state.oauth_authorization_url = None
        mock_event.state.oauth_state_token = None
        mock_event.state.error_message = None
        mock_event.state.progress_percent = None
        mock_event.channel_name = "whatsapp"
        mock_event.credentials = None

        mock_event2 = MagicMock()
        mock_event2.timestamp = 1234567891.0
        mock_event2.state.status = LoginStatus.SUCCESS
        mock_event2.state.method = LoginMethod.QR_CODE
        mock_event2.state.qr_code_base64 = None
        mock_event2.state.qr_expires_at = None
        mock_event2.state.oauth_authorization_url = None
        mock_event2.state.oauth_state_token = None
        mock_event2.state.error_message = None
        mock_event2.state.progress_percent = None
        mock_event2.channel_name = "whatsapp"
        mock_event2.credentials = {"token": "xyz"}

        async def fake_login(**kwargs):
            yield mock_event
            yield mock_event2

        mock_ch.start_login = fake_login

        with patch("app.api.channels.login.channel_gateway") as gw:
            gw.bus.channels.get.return_value = mock_ch

            # First create a session
            resp = client.post(
                "/api/v1/channels/whatsapp/login/start",
                json={"method": "qr_code"},
                headers={"Authorization": "Bearer test"},
            )
            assert resp.status_code == 200
            session_id = resp.json()["session_id"]

            # Then stream
            resp = client.get(
                f"/api/v1/channels/login/{session_id}/stream",
                headers={"Authorization": "Bearer test"},
            )
            assert resp.status_code == 200
            body = resp.text

        # Verify event: login_state prefix exists
        assert "event: login_state" in body
        assert "data: " in body
        # orjson serializes without spaces
        assert '"qr_code_base64":"ABC123"' in body


class TestCancelLogin:
    """Tests for DELETE /channels/login/{session_id}."""

    def test_cancel_login_success(self, client):
        mock_ch = _make_mock_channel(status=ChannelStatus.RUNNING)

        with patch("app.api.channels.login.channel_gateway") as gw:
            gw.bus.channels.get.return_value = mock_ch

            # Create session
            resp = client.post(
                "/api/v1/channels/whatsapp/login/start",
                json={"method": "qr_code"},
                headers={"Authorization": "Bearer test"},
            )
            session_id = resp.json()["session_id"]

            # Cancel
            resp = client.delete(
                f"/api/v1/channels/login/{session_id}",
                headers={"Authorization": "Bearer test"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "cancelled"
            mock_ch.cancel_login.assert_called_once()

    def test_cancel_nonexistent_session(self, client):
        with patch("app.api.channels.login.channel_gateway"):
            resp = client.delete(
                "/api/v1/channels/login/nonexistent-id",
                headers={"Authorization": "Bearer test"},
            )
        assert resp.status_code == 404


class TestOAuth2Callback:
    """Tests for GET /channels/{channel_id}/login/oauth2/callback."""

    def test_callback_delegates_to_channel(self, client):
        """Callback should call channel.handle_oauth2_callback with code & state."""
        mock_ch = _make_mock_channel(status=ChannelStatus.RUNNING)
        mock_ch.handle_oauth2_callback = AsyncMock()

        with patch("app.api.channels.login.channel_gateway") as gw:
            gw.bus.channels.get.return_value = mock_ch
            resp = client.get(
                "/api/v1/channels/google/login/oauth2/callback",
                params={"code": "auth123", "state": "state456"},
                headers={"Authorization": "Bearer test"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        mock_ch.handle_oauth2_callback.assert_called_once_with(
            code="auth123",
            state="state456",
            error=None,
        )

    def test_callback_channel_not_found(self, client):
        with patch("app.api.channels.login.channel_gateway") as gw:
            gw.bus.channels.get.return_value = None
            resp = client.get(
                "/api/v1/channels/unknown/login/oauth2/callback",
                params={"code": "c", "state": "s"},
                headers={"Authorization": "Bearer test"},
            )
        assert resp.status_code == 404

    def test_callback_missing_params(self, client):
        """Missing code or state returns 400."""
        mock_ch = _make_mock_channel(status=ChannelStatus.RUNNING)
        with patch("app.api.channels.login.channel_gateway") as gw:
            gw.bus.channels.get.return_value = mock_ch
            resp = client.get(
                "/api/v1/channels/google/login/oauth2/callback",
                params={"code": "auth123"},
                headers={"Authorization": "Bearer test"},
            )
        assert resp.status_code == 400

    def test_callback_with_error(self, client):
        """OAuth2 error parameter returns error status without calling channel."""
        mock_ch = _make_mock_channel(status=ChannelStatus.RUNNING)
        mock_ch.handle_oauth2_callback = AsyncMock()
        with patch("app.api.channels.login.channel_gateway") as gw:
            gw.bus.channels.get.return_value = mock_ch
            resp = client.get(
                "/api/v1/channels/google/login/oauth2/callback",
                params={"error": "access_denied"},
                headers={"Authorization": "Bearer test"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
        mock_ch.handle_oauth2_callback.assert_not_called()

    def test_callback_not_implemented(self, client):
        """Channel without OAuth2 support returns 400."""
        mock_ch = _make_mock_channel(status=ChannelStatus.RUNNING)
        mock_ch.handle_oauth2_callback = AsyncMock(side_effect=NotImplementedError("no OAuth2"))

        with patch("app.api.channels.login.channel_gateway") as gw:
            gw.bus.channels.get.return_value = mock_ch
            resp = client.get(
                "/api/v1/channels/wechat/login/oauth2/callback",
                params={"code": "c", "state": "s"},
                headers={"Authorization": "Bearer test"},
            )
        assert resp.status_code == 400
        assert "does not support" in resp.json()["detail"]
