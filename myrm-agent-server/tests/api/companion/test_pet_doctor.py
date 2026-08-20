from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app


@pytest.fixture
def companion_app():
    return build_minimal_app(preset="companion")


@pytest.mark.asyncio
async def test_companion_doctor_reports_feature_gate(companion_app) -> None:
    from myrm_agent_harness.core.features import init_features

    from app.services.features.registration import register_all_features

    register_all_features()
    init_features(overrides={"companion_mode": False})

    async with AsyncClient(transport=ASGITransport(app=companion_app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/companion/doctor")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["ready"] is False
        check_ids = {item["id"] for item in payload["checks"]}
        assert "feature_gate.companion_mode" in check_ids
