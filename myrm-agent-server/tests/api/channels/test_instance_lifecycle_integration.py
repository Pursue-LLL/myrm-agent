"""Integration: real channel instance create/delete lifecycle via HTTP API.

Covers the full wiring behind the settings "delete instance" confirmation:
``POST /instances`` -> real ``channel_factory.create_channel_instance`` -> real
``ChannelGateway.add_channel`` -> persisted instance list -> ``DELETE /instances``
-> real ``ChannelGateway.remove_channel`` -> persisted list + credentials cleanup.

Key paths (factory, gateway, UserConfig persistence) are real, not mocked.
A ``WebhookChannel`` is used because it needs no external credentials.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from httpx import ASGITransport

from app.channels.core.gateway import ChannelGateway
from app.core.channel_bridge.channel_factory import (
    _INSTANCES_CONFIG_KEY,
    load_persisted_instances,
)
from app.database.connection import get_session
from app.database.models import UserConfig
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="channels_local")

_INSTANCES_ENDPOINT = "/api/v1/channels/manage/instances"


async def _clear_instance_state() -> None:
    """Remove persisted instance list + leftover credentials rows."""
    from sqlalchemy import delete, select

    async with get_session() as session:
        rows = (
            await session.execute(
                select(UserConfig).where(UserConfig.config_key == _INSTANCES_CONFIG_KEY)
            )
        ).scalars().all()
        for row in rows:
            await session.delete(row)
        await session.execute(
            delete(UserConfig).where(UserConfig.config_key.like("webhook_%Credentials"))
        )
        await session.execute(
            delete(UserConfig).where(UserConfig.config_key.like("wechat_%Credentials"))
        )
        await session.commit()


@pytest.fixture
async def gateway() -> ChannelGateway:
    gw = ChannelGateway()
    await gw.start()
    try:
        yield gw
    finally:
        await gw.stop()


@pytest.fixture
async def client(gateway: ChannelGateway, monkeypatch: pytest.MonkeyPatch) -> httpx.AsyncClient:
    """Patch the app-level singleton to the real gateway in this test."""
    monkeypatch.setattr("app.core.channel_bridge.channel_gateway", gateway)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as c:
        yield c


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_webhook_instance_then_delete(
    client: httpx.AsyncClient, gateway: ChannelGateway
) -> None:
    """Create a webhook instance via the API, verify it is live in the real
    gateway bus, then delete it and verify full cleanup."""
    await _clear_instance_state()
    try:
        created = await client.post(
            _INSTANCES_ENDPOINT,
            json={"channelType": "webhook", "displayName": "E2E Hook"},
        )
        assert created.status_code == 201
        body = created.json()
        instance_id = body["instanceId"]
        assert instance_id
        assert body["channelName"] == f"webhook_{instance_id}"
        assert body["status"] in ("running", "idle", "stopped")

        # Instance is live in the real gateway bus.
        assert f"webhook_{instance_id}" in gateway.bus.channels

        # Persisted instance list contains the new instance.
        persisted = await load_persisted_instances()
        assert any(i.get("instanceId") == instance_id for i in persisted)

        deleted = await client.delete(f"{_INSTANCES_ENDPOINT}/{instance_id}")
        assert deleted.status_code == 204

        # Removed from the real gateway bus and the persisted list.
        assert f"webhook_{instance_id}" not in gateway.bus.channels
        persisted_after = await load_persisted_instances()
        assert all(i.get("instanceId") != instance_id for i in persisted_after)
    finally:
        await _clear_instance_state()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_wechat_instance_then_delete(
    client: httpx.AsyncClient, gateway: ChannelGateway
) -> None:
    """Create a WeChat (iLink) instance via the API, then delete it — the same
    channel type the delete-confirmation E2E exercises."""
    await _clear_instance_state()
    try:
        created = await client.post(
            _INSTANCES_ENDPOINT,
            json={"channelType": "wechat", "displayName": "E2E WeChat"},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        instance_id = body["instanceId"]
        assert instance_id
        assert body["channelName"] == f"wechat_{instance_id}"

        assert f"wechat_{instance_id}" in gateway.bus.channels
        persisted = await load_persisted_instances()
        assert any(i.get("instanceId") == instance_id for i in persisted)

        listed = await client.get(f"{_INSTANCES_ENDPOINT}?channel_type=wechat")
        assert listed.status_code == 200, listed.text
        listed_body = listed.json()
        assert isinstance(listed_body, list), listed_body
        listed_ids = [i.get("instanceId") for i in listed_body if isinstance(i, dict)]
        # The instance list must expose the same bare instance id the UI passes
        # to DELETE, otherwise the delete-confirmation flow removes nothing.
        assert instance_id in listed_ids, f"listed ids: {listed_ids}"

        deleted = await client.delete(f"{_INSTANCES_ENDPOINT}/{instance_id}")
        assert deleted.status_code == 204, deleted.text

        assert f"wechat_{instance_id}" not in gateway.bus.channels
        persisted_after = await load_persisted_instances()
        assert all(i.get("instanceId") != instance_id for i in persisted_after)
    finally:
        await _clear_instance_state()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_missing_instance_returns_404(client: httpx.AsyncClient) -> None:
    """Deleting a never-registered instance id must answer 404."""
    missing = f"missing_{uuid.uuid4().hex[:8]}"
    resp = await client.delete(f"{_INSTANCES_ENDPOINT}/{missing}")
    assert resp.status_code == 404
