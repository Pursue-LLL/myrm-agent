"""Omni-Config validation for searchServices priority chain."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.database.connection import get_session
from app.database.models import ConfigAuditLog, UserConfig
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="config")
client = TestClient(app)


async def _clear_config_tables(session) -> None:
    bind = await session.connection()

    def _delete_if_present(sync_conn) -> None:
        table_names = set(inspect(sync_conn).get_table_names())
        if "config_audit_logs" in table_names:
            sync_conn.execute(ConfigAuditLog.__table__.delete())
        if "user_configs" in table_names:
            sync_conn.execute(UserConfig.__table__.delete())

    await bind.run_sync(_delete_if_present)
    await session.commit()


@pytest.fixture(autouse=True)
async def cleanup_db():
    async with get_session() as session:
        await _clear_config_tables(session)
    yield
    async with get_session() as session:
        await _clear_config_tables(session)


@pytest.mark.asyncio
async def test_search_services_rejects_unknown_slug() -> None:
    payload = {
        "value": {
            "searchServiceConfigs": [
                {
                    "id": "bad",
                    "enabled": True,
                    "priority": 1,
                    "search_service": "unknown_provider",
                    "api_key": "k",
                    "createdAt": 1,
                }
            ]
        },
        "device_id": "test_device",
    }
    response = client.put("/api/v1/config/searchServices", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_services_rejects_duplicate_enabled_priority() -> None:
    payload = {
        "value": {
            "searchServiceConfigs": [
                {
                    "id": "a",
                    "enabled": True,
                    "priority": 1,
                    "search_service": "tavily",
                    "api_key": "k1",
                    "createdAt": 1,
                },
                {
                    "id": "b",
                    "enabled": True,
                    "priority": 1,
                    "search_service": "perplexity",
                    "api_key": "k2",
                    "createdAt": 2,
                },
            ]
        },
        "device_id": "test_device",
    }
    response = client.put("/api/v1/config/searchServices", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_services_accepts_valid_priority_chain() -> None:
    payload = {
        "value": {
            "searchServiceConfigs": [
                {
                    "id": "a",
                    "enabled": True,
                    "priority": 1,
                    "search_service": "tavily",
                    "api_key": "k1",
                    "createdAt": 1,
                },
                {
                    "id": "b",
                    "enabled": False,
                    "priority": 2,
                    "search_service": "searxng",
                    "api_base": "http://127.0.0.1:8081",
                    "createdAt": 2,
                },
            ]
        },
        "device_id": "test_device",
    }
    response = client.put("/api/v1/config/searchServices", json=payload)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_search_services_accepts_selectable_volcengine_doubao() -> None:
    payload = {
        "value": {
            "searchServiceConfigs": [
                {
                    "id": "volc",
                    "enabled": True,
                    "priority": 1,
                    "search_service": "volcengine_doubao",
                    "api_key": "k",
                    "createdAt": 1,
                }
            ]
        },
        "device_id": "test_device",
    }
    response = client.put("/api/v1/config/searchServices", json=payload)
    assert response.status_code == 200
