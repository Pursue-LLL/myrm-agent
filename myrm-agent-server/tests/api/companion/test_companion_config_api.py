from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.database.connection import get_session
from app.database.models import UserConfig
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="companion")
@pytest.mark.asyncio
async def test_companion_config_flow() -> None:
    """Verify that companion customization config can be saved, updated, and retrieved from DB."""
    from myrm_agent_harness.core.features import init_features

    from app.services.features.registration import register_all_features

    register_all_features()
    init_features(overrides={"companion_mode": True})

    # Clean up first to ensure a clean slate
    async with get_session() as session:
        await session.execute(delete(UserConfig).where(UserConfig.config_key == "companion_config"))
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. GET config when empty (should return empty config structure)
        resp = await ac.get("/api/v1/companion/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["value"]["name"] is None
        assert data["value"]["species"] is None
        assert data["value"]["hat"] is None
        assert data["value"]["palette_theme"] is None

        # 2. SET config with custom values
        set_payload = {
            "value": {
                "name": "Ferris",
                "species": "Crab",
                "hat": "Cowboy Hat",
                "palette_theme": "Laserwave",
            },
            "deviceId": "test_device_1",
        }
        resp = await ac.post("/api/v1/companion/config", json=set_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["value"]["name"] == "Ferris"
        assert data["value"]["species"] == "Crab"
        assert data["value"]["hat"] == "Cowboy Hat"
        assert data["value"]["palette_theme"] == "Laserwave"
        assert data["version"] is not None

        # 3. GET config again to check persistence
        resp = await ac.get("/api/v1/companion/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["value"]["name"] == "Ferris"
        assert data["value"]["species"] == "Crab"
        assert data["value"]["hat"] == "Cowboy Hat"
        assert data["value"]["palette_theme"] == "Laserwave"
