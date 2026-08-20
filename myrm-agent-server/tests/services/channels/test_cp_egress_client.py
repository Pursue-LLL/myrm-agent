"""Tests for CP egress client success semantics."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.channels import cp_egress_client


@pytest.mark.asyncio
async def test_send_via_control_plane_returns_none_when_message_id_missing() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "sent", "message_id": None}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with (
        patch.object(cp_egress_client.settings.control_plane, "url", "https://cp.example"),
        patch.dict(
            "os.environ",
            {
                "CONTROL_PLANE_TELEMETRY_TOKEN": "token",
                "SANDBOX_ID": "sandbox-1",
            },
        ),
        patch(
            "app.services.channels.cp_egress_client.httpx.AsyncClient",
            return_value=mock_client,
        ),
    ):
        result = await cp_egress_client.send_via_control_plane(
            channel="feishu",
            chat_id="chat-1",
            content="hello",
            tenant_id="tenant-1",
        )

    assert result is None


@pytest.mark.asyncio
async def test_send_via_control_plane_returns_message_id_on_success() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "sent", "message_id": "om_abc123"}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with (
        patch.object(cp_egress_client.settings.control_plane, "url", "https://cp.example"),
        patch.dict(
            "os.environ",
            {
                "CONTROL_PLANE_TELEMETRY_TOKEN": "token",
                "SANDBOX_ID": "sandbox-1",
            },
        ),
        patch(
            "app.services.channels.cp_egress_client.httpx.AsyncClient",
            return_value=mock_client,
        ),
    ):
        result = await cp_egress_client.send_via_control_plane(
            channel="feishu",
            chat_id="chat-1",
            content="hello",
            tenant_id="tenant-1",
        )

    assert result == "om_abc123"
