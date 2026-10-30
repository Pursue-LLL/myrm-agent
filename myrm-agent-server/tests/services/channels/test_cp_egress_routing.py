"""Unit tests for CP egress routing predicates."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.settings import settings
from app.services.channels import cp_egress_client


def test_should_route_false_when_not_sandbox() -> None:
    caps = MagicMock(is_sandbox_instance=False)
    with patch(
        "app.services.channels.cp_egress_client.get_deployment_capabilities",
        return_value=caps,
    ):
        assert cp_egress_client.should_route_via_control_plane("feishu") is False


def test_should_route_true_for_saas_feishu() -> None:
    caps = MagicMock(is_sandbox_instance=True)
    with patch(
        "app.services.channels.cp_egress_client.get_deployment_capabilities",
        return_value=caps,
    ):
        assert cp_egress_client.should_route_via_control_plane("feishu") is True


@pytest.mark.parametrize("channel", ["whatsapp", "web_chat", ""])
def test_should_route_false_for_a_channel_outside_the_hosted_set(channel: str) -> None:
    caps = MagicMock(is_sandbox_instance=True)
    with patch(
        "app.services.channels.cp_egress_client.get_deployment_capabilities",
        return_value=caps,
    ):
        assert cp_egress_client.should_route_via_control_plane(channel) is False


@pytest.mark.asyncio
async def test_send_via_control_plane_missing_config() -> None:
    with (
        patch.object(settings.control_plane, "url", ""),
        patch.dict("os.environ", {}, clear=True),
    ):
        result = await cp_egress_client.send_via_control_plane(
            channel="feishu",
            chat_id="c1",
            content="hi",
            tenant_id="t1",
        )
    assert result is None


@pytest.mark.asyncio
async def test_send_via_control_plane_http_error() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 502
    mock_response.text = "bad gateway"

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch.object(settings.control_plane, "url", "https://cp.example"),
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
            chat_id="c1",
            content="hi",
            tenant_id="t1",
        )
    assert result is None
