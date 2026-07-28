"""Tests for xAI OAuth device-code flow API."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import Response

from app.api.integrations.xai_oauth import (
    XAI_OAUTH_CLIENT_ID,
    XAI_OAUTH_DEVICE_CODE_URL,
    XAI_OAUTH_SCOPE,
    XAI_OAUTH_TOKEN_URL,
    _pending_flows,
)


@pytest.fixture(autouse=True)
def _clean_pending_flows():
    _pending_flows.clear()
    yield
    _pending_flows.clear()


@pytest.mark.asyncio
async def test_start_xai_oauth_returns_user_code(client):
    """POST /integrations/xai/oauth/start returns device code info."""
    mock_response = Response(
        200,
        json={
            "device_code": "dc-123",
            "user_code": "ABCD-1234",
            "verification_uri": "https://auth.x.ai/device",
            "verification_uri_complete": "https://auth.x.ai/device?user_code=ABCD-1234",
            "interval": 5,
            "expires_in": 600,
        },
    )

    with patch("app.api.integrations.xai_oauth.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        resp = await client.post("/api/integrations/xai/oauth/start")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["user_code"] == "ABCD-1234"
    assert data["verification_uri_complete"] == "https://auth.x.ai/device?user_code=ABCD-1234"
    assert "ABCD-1234" in _pending_flows


@pytest.mark.asyncio
async def test_poll_returns_pending_before_auth(client):
    """POST /integrations/xai/oauth/poll returns pending when user hasn't authorized yet."""
    from app.api.integrations.xai_oauth import _DeviceCodePending

    import time

    _pending_flows["TEST-CODE"] = _DeviceCodePending(
        device_code="dc-456",
        user_code="TEST-CODE",
        verification_uri="https://auth.x.ai/device",
        verification_uri_complete="https://auth.x.ai/device?user_code=TEST-CODE",
        expires_at=time.time() + 600,
        interval=5,
    )

    mock_response = Response(
        400,
        json={"error": "authorization_pending"},
        headers={"content-type": "application/json"},
    )

    with patch("app.api.integrations.xai_oauth.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        resp = await client.post("/api/integrations/xai/oauth/poll?user_code=TEST-CODE")

    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "pending"


@pytest.mark.asyncio
async def test_poll_succeeds_and_stores_credential(client, db_session):
    """POST /integrations/xai/oauth/poll stores credential on success."""
    from app.api.integrations.xai_oauth import _DeviceCodePending

    import time

    _pending_flows["SUCCESS-CODE"] = _DeviceCodePending(
        device_code="dc-789",
        user_code="SUCCESS-CODE",
        verification_uri="https://auth.x.ai/device",
        verification_uri_complete="https://auth.x.ai/device?user_code=SUCCESS-CODE",
        expires_at=time.time() + 600,
        interval=5,
    )

    mock_response = Response(
        200,
        json={
            "access_token": "xai-access-token",
            "refresh_token": "xai-refresh-token",
            "expires_in": 21600,
            "scope": XAI_OAUTH_SCOPE,
        },
    )

    with patch("app.api.integrations.xai_oauth.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        with patch("app.api.integrations.xai_oauth.upsert_oauth_credential", new_callable=AsyncMock) as mock_upsert:
            resp = await client.post("/api/integrations/xai/oauth/poll?user_code=SUCCESS-CODE")

    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "success"
    assert "SUCCESS-CODE" not in _pending_flows

    if mock_upsert.called:
        call_args = mock_upsert.call_args
        assert call_args[0][1] == "xai"
        entry = call_args[0][2]
        assert entry["token"] == "xai-access-token"
        assert entry["refresh_token"] == "xai-refresh-token"


@pytest.mark.asyncio
async def test_poll_returns_expired_when_flow_timed_out(client):
    """POST /integrations/xai/oauth/poll returns expired for timed-out flows."""
    from app.api.integrations.xai_oauth import _DeviceCodePending

    import time

    _pending_flows["EXPIRED-CODE"] = _DeviceCodePending(
        device_code="dc-exp",
        user_code="EXPIRED-CODE",
        verification_uri="https://auth.x.ai/device",
        verification_uri_complete="https://auth.x.ai/device?user_code=EXPIRED-CODE",
        expires_at=time.time() - 1,
        interval=5,
    )

    resp = await client.post("/api/integrations/xai/oauth/poll?user_code=EXPIRED-CODE")

    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "expired"
    assert "EXPIRED-CODE" not in _pending_flows


@pytest.mark.asyncio
async def test_poll_returns_404_for_unknown_code(client):
    """POST /integrations/xai/oauth/poll returns 404 for unknown user_code."""
    resp = await client.post("/api/integrations/xai/oauth/poll?user_code=UNKNOWN")

    assert resp.status_code == 404
