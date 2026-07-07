"""API integration tests for idempotent config sync."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_session
from app.database.models import ConfigAuditLog, UserConfig
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="config")
client = TestClient(app)


@pytest.fixture(autouse=True)
async def cleanup_db() -> None:
    async with get_session() as session:
        await session.execute(ConfigAuditLog.__table__.delete())
        await session.execute(UserConfig.__table__.delete())
        await session.commit()
    yield
    async with get_session() as session:
        await session.execute(ConfigAuditLog.__table__.delete())
        await session.execute(UserConfig.__table__.delete())
        await session.commit()


@pytest.mark.asyncio
async def test_sync_idempotent_when_content_matches_despite_stale_version() -> None:
    initial = {
        "value": {"fetchRawWebpage": True, "enableMemory": True},
        "device_id": "device-a",
    }
    created = client.put("/api/v1/config/personalSettings", json=initial)
    assert created.status_code == 200
    current_version = created.json()["version"]

    bumped = {
        "value": {"fetchRawWebpage": True, "enableMemory": False},
        "device_id": "device-b",
    }
    updated = client.put("/api/v1/config/personalSettings", json=bumped)
    assert updated.status_code == 200
    assert updated.json()["version"] != current_version

    sync_payload = {
        "changes": [
            {
                "key": "personalSettings",
                "value": {"fetchRawWebpage": True, "enableMemory": True},
                "expectedVersion": current_version,
                "timestamp": 1,
            }
        ],
        "deviceId": "device-a",
    }
    sync_res = client.post("/api/v1/config/sync", json=sync_payload)
    assert sync_res.status_code == 200
    body = sync_res.json()
    assert body["success"] is False
    assert "personalSettings" in body["conflicts"]

    idempotent_payload = {
        "value": {"fetchRawWebpage": True, "enableMemory": False},
        "expectedVersion": current_version,
        "device_id": "device-a",
    }
    idempotent_res = client.put("/api/v1/config/personalSettings", json=idempotent_payload)
    assert idempotent_res.status_code == 200
    assert idempotent_res.json()["version"] == updated.json()["version"]


@pytest.mark.asyncio
async def test_sync_reports_conflict_when_content_differs() -> None:
    created = client.put(
        "/api/v1/config/personalSettings",
        json={"value": {"fetchRawWebpage": True}, "device_id": "device-a"},
    )
    assert created.status_code == 200
    version = created.json()["version"]

    client.put(
        "/api/v1/config/personalSettings",
        json={"value": {"fetchRawWebpage": False}, "device_id": "device-b"},
    )

    sync_res = client.post(
        "/api/v1/config/sync",
        json={
            "changes": [
                {
                    "key": "personalSettings",
                    "value": {"fetchRawWebpage": True},
                    "expectedVersion": version,
                    "timestamp": 1,
                }
            ],
            "deviceId": "device-a",
        },
    )
    assert sync_res.status_code == 200
    assert sync_res.json()["conflicts"] == ["personalSettings"]
