"""Integration: channel status API merges real ingress-requirement supplement."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.channels.types.status import ChannelStatus
from app.core.channel_bridge import channel_gateway
from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.core.infra.ingress_requirement import invalidate_ingress_requirement_cache
from app.database.connection import get_session
from app.database.models import UserConfig
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="channels_local")


async def _seed_line_credentials() -> None:
    async with get_session() as session:
        await session.execute(UserConfig.__table__.delete())
        session.add(
            UserConfig(
                id=str(uuid.uuid4()),
                config_key="lineCredentials",
                config_value={"channelAccessToken": "test-token", "channelSecret": "secret"},
                version="test_1",
                last_device_id="test-device",
                is_encrypted=False,
            )
        )
        await session.commit()
    invalidate_user_configs_cache()
    invalidate_ingress_requirement_cache()


async def _clear_credentials() -> None:
    async with get_session() as session:
        await session.execute(UserConfig.__table__.delete())
        await session.commit()
    invalidate_user_configs_cache()
    invalidate_ingress_requirement_cache()


@pytest.fixture(autouse=True)
def _credentials_fixture() -> None:
    asyncio.run(_seed_line_credentials())
    yield
    asyncio.run(_clear_credentials())


@pytest.fixture
def client() -> TestClient:
    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client


def test_channel_status_injects_ingress_warning_for_inbound(client: TestClient) -> None:
    """GET /channels/manage/status uses resolve_ingress_requirement (no mock) + supplement."""
    mock_bus = MagicMock()
    mock_bus.get_channel.return_value = None

    with (
        patch.object(channel_gateway, "get_status", return_value={"line": ChannelStatus.STOPPED}),
        patch.object(channel_gateway, "bus", mock_bus),
        patch("app.channels.providers.registry.probe_sdk_channel_issues", return_value={}),
    ):
        response = client.get("/api/v1/channels/manage/status")

    assert response.status_code == 200
    line = next((item for item in response.json() if item["name"] == "line"), None)
    assert line is not None
    ingress_issues = [issue for issue in line["issues"] if "Ingress" in issue["message"]]
    assert len(ingress_issues) == 1
    assert ingress_issues[0]["severity"] == "warning"
    assert ingress_issues[0]["kind"] == "config"
