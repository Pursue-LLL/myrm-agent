"""GET /companion/evolution-status: the body is the status itself, not wrapped in an envelope."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.core.features import init_features

from app.services.features.registration import register_all_features
from tests.support.minimal_app import build_minimal_app

STATUS_KEYS = {"metrics", "current_rarity", "max_reachable_rarity", "can_evolve", "next_threshold"}


@pytest.fixture
def companion_app() -> FastAPI:
    register_all_features()
    init_features(overrides={"companion_mode": True})
    return build_minimal_app(preset="companion")


@pytest.mark.asyncio
async def test_status_of_a_fresh_account_is_the_flat_status(companion_app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=companion_app), base_url="http://test") as client:
        response = await client.get("/api/v1/companion/evolution-status", params={"current_rarity": "Common"})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == STATUS_KEYS
    assert body["metrics"] == {"conversations": 0, "active_days": 0, "total_messages": 0}
    assert body["current_rarity"] == "Common"
    assert body["max_reachable_rarity"] == "Common"
    assert body["can_evolve"] is False
    assert set(body["next_threshold"]) >= {"conversations", "active_days", "total_messages"}


@pytest.mark.asyncio
async def test_status_refuses_an_unknown_rarity(companion_app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=companion_app), base_url="http://test") as client:
        response = await client.get("/api/v1/companion/evolution-status", params={"current_rarity": "Mythic"})

    assert response.status_code == 400
