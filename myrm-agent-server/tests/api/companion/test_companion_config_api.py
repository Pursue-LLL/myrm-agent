from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.database.models import UserConfig
from tests.support.minimal_app import build_minimal_app


@pytest.fixture
def companion_app():
    return build_minimal_app(preset="companion")


@pytest.mark.asyncio
async def test_companion_config_flow(companion_app) -> None:
    """Verify that companion customization config can be saved, updated, and retrieved from DB."""
    from myrm_agent_harness.core.features import init_features

    from app.database.connection import get_session
    from app.services.features.registration import register_all_features

    register_all_features()
    init_features(overrides={"companion_mode": True})

    async with get_session() as session:
        await session.execute(delete(UserConfig).where(UserConfig.config_key == "companion_config"))
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=companion_app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/companion/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["value"]["name"] is None
        assert data["value"]["species"] is None
        assert data["value"]["hat"] is None
        assert data["value"]["sprite"] is None

        set_payload = {
            "value": {
                "name": "Ferris",
                "species": "Crab",
                "hat": "Cowboy Hat",
                "sprite": {
                    "pet_slug": "nous-girl",
                    "content_sha256": "deadbeef",
                    "display_name": "Nous Girl",
                },
            },
            "deviceId": "test_device_1",
        }
        resp = await ac.post("/api/v1/companion/config", json=set_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["value"]["name"] == "Ferris"
        assert data["value"]["species"] == "Crab"
        assert data["value"]["hat"] == "Cowboy Hat"
        assert data["value"]["sprite"]["pet_slug"] == "nous-girl"
        assert data["value"]["sprite"]["content_sha256"] == "deadbeef"
        assert data["value"]["sprite"]["display_name"] == "Nous Girl"
        assert data["version"] is not None

        resp = await ac.get("/api/v1/companion/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["value"]["name"] == "Ferris"
        assert data["value"]["species"] == "Crab"
        assert data["value"]["hat"] == "Cowboy Hat"
        assert data["value"]["sprite"]["pet_slug"] == "nous-girl"
        assert data["value"]["sprite"]["display_name"] == "Nous Girl"
