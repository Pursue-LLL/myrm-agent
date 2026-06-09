import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_session
from app.database.models import ConfigAuditLog, UserConfig
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="config")
from app.schemas.config import PersonalSettingsConfigValue

client = TestClient(app)


def test_personal_settings_schema_ui_sections() -> None:
    schema = PersonalSettingsConfigValue.model_json_schema()
    properties = schema["properties"]
    assert properties["fetchRawWebpage"]["x-ui-section"] == "preferences"
    assert properties["fetchRawWebpage"]["x-ui-group"] == "advanced"
    assert properties["generateSearchSuggestions"]["x-ui-group"] == "basic"
    assert properties["enableCostEstimation"]["x-ui-visible-if"] == "local"
    assert properties["enableCacheBreakNotification"]["x-ui-requires-field"] == "enableCostEstimation"
    assert properties["webTtsProvider"]["x-ui-section"] == "voice"
    assert set(properties["webTtsProvider"]["enum"]) == {
        "browser",
        "openai",
        "elevenlabs",
        "fish_audio",
        "minimax",
        "edge",
    }
    assert properties["enableWebNotifications"]["x-ui-section"] == "notifications"
    assert properties["enableCompletionSound"]["x-ui-section"] == "notifications"
    assert properties["enableMemory"]["x-ui-section"] == "memory"
    assert properties["systemInstructions"]["x-ui-section"] == "personalization"
    assert properties["notificationDeliveries"]["x-ui-section"] == "notifications"
    assert properties["publicIngressBaseUrl"]["x-ui-section"] == "system"


@pytest.fixture(autouse=True)
async def cleanup_db():
    # Clean up before test
    async with get_session() as session:
        await session.execute(ConfigAuditLog.__table__.delete())
        await session.execute(UserConfig.__table__.delete())
        await session.commit()
    yield
    # Clean up after test
    async with get_session() as session:
        await session.execute(ConfigAuditLog.__table__.delete())
        await session.execute(UserConfig.__table__.delete())
        await session.commit()


@pytest.mark.asyncio
async def test_get_config_schema():
    # Test valid key
    response = client.get("/api/v1/config/schema/personalSettings")
    assert response.status_code == 200
    schema = response.json()
    assert "properties" in schema
    assert "systemInstructions" in schema["properties"]

    # Test invalid key
    response = client.get("/api/v1/config/schema/invalidKey")
    assert response.status_code == 400

    # Test valid key but not migrated to Omni-Config
    response = client.get("/api/v1/config/schema/chatSettings")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_set_config_with_validation():
    # Valid payload
    payload = {
        "value": {
            "fetchRawWebpage": True,
            "enableMemory": False,
        },
        "device_id": "test_device",
    }
    response = client.put("/api/v1/config/personalSettings", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["value"]["fetchRawWebpage"] is True
    # Pydantic validation should populate defaults for missing fields
    assert "systemInstructions" in data["value"]
    assert data["value"]["systemInstructions"] == ""

    # Invalid payload (wrong type)
    invalid_payload = {
        "value": {
            "fetchRawWebpage": "not_a_boolean",
        },
        "device_id": "test_device",
    }
    response = client.put("/api/v1/config/personalSettings", json=invalid_payload)
    assert response.status_code == 422
    assert "validation failed" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_sync_config_uses_omni_validation_without_500():
    valid_payload = {
        "changes": [
            {
                "key": "personalSettings",
                "value": {
                    "fetchRawWebpage": True,
                    "enableMemory": False,
                },
                "expectedVersion": None,
                "timestamp": 1,
            }
        ],
        "deviceId": "test_device",
    }
    response = client.post("/api/v1/config/sync", json=valid_payload)

    assert response.status_code == 200
    assert response.json()["success"] is True

    stored = client.get("/api/v1/config/personalSettings")
    assert stored.status_code == 200
    stored_value = stored.json()["value"]
    assert stored_value["fetchRawWebpage"] is True
    assert stored_value["systemInstructions"] == ""

    invalid_payload = {
        "changes": [
            {
                "key": "personalSettings",
                "value": {
                    "fetchRawWebpage": "not_a_boolean",
                },
                "expectedVersion": stored.json()["version"],
                "timestamp": 2,
            },
            {
                "key": "searchServices",
                "value": {
                    "searchServiceConfigs": [
                        {
                            "id": "bad-search",
                            "role": "primary",
                            "search_service": "unknown",
                            "createdAt": 1,
                        }
                    ],
                },
                "expectedVersion": None,
                "timestamp": 3,
            },
        ],
        "deviceId": "test_device",
    }
    invalid_response = client.post("/api/v1/config/sync", json=invalid_payload)

    assert invalid_response.status_code == 422
    detail = invalid_response.json()["detail"]
    assert detail["message"] == "Configuration sync validation failed"
    assert [item["key"] for item in detail["validation_errors"]] == [
        "personalSettings",
        "searchServices",
    ]


@pytest.mark.asyncio
async def test_config_history_and_rollback():
    # 1. Set initial config
    payload1 = {
        "value": {
            "fetchRawWebpage": True,
            "systemInstructions": "v1",
        },
        "device_id": "device1",
    }
    res1 = client.put("/api/v1/config/personalSettings", json=payload1)
    assert res1.status_code == 200
    version1 = res1.json()["version"]

    # 2. Update config
    payload2 = {
        "value": {
            "fetchRawWebpage": False,
            "systemInstructions": "v2",
        },
        "device_id": "device1",
    }
    res2 = client.put("/api/v1/config/personalSettings", json=payload2)
    assert res2.status_code == 200
    version2 = res2.json()["version"]

    # 3. Get history
    history_res = client.get("/api/v1/config/personalSettings/history")
    assert history_res.status_code == 200
    history = history_res.json()
    assert len(history) >= 2

    # History is ordered by created_at desc
    assert history[0]["version"] == version2
    assert history[0]["new_value"]["systemInstructions"] == "v2"
    assert history[1]["version"] == version1
    assert history[1]["new_value"]["systemInstructions"] == "v1"

    # 4. Rollback to version 1
    rollback_res = client.post(f"/api/v1/config/personalSettings/rollback/{version1}?device_id=device2")
    assert rollback_res.status_code == 200
    rollback_data = rollback_res.json()
    assert rollback_data["value"]["systemInstructions"] == "v1"
    assert rollback_data["value"]["fetchRawWebpage"] is True

    # Rollback should create a new version
    assert rollback_data["version"] != version1
    assert rollback_data["version"] != version2

    # 5. Check history again
    history_res2 = client.get("/api/v1/config/personalSettings/history")
    assert history_res2.status_code == 200
    history2 = history_res2.json()
    assert history2[0]["new_value"]["systemInstructions"] == "v1"
    assert history2[0]["device_id"] == "device2"
