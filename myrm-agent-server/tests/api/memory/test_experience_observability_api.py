# [POS]: tests/api/memory/test_experience_observability_api.py
# [INPUT]: app.api.memory.experience_observability_router, FastAPI app
# [OUTPUT]: Integration API tests for ZeroRefactorHostLifecyclePluginAndExperienceObservabilitySuite (Item 108)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.experience_observability_router import (
    router as experience_observability_router,
)
from app.services.memory.experience_observability_service import (
    ExperienceObservabilityService,
    get_experience_observability_service,
)


@pytest.fixture
def isolated_service() -> ExperienceObservabilityService:
    """Provides an isolated in-memory ExperienceObservabilityService instance."""
    return ExperienceObservabilityService()


@pytest.fixture
def test_app(isolated_service: ExperienceObservabilityService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(experience_observability_router, prefix="/api/memory")
    app.dependency_overrides[get_experience_observability_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_get_dashboard_api(test_app: FastAPI) -> None:
    """Validate full dashboard triad view retrieval via REST API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/memory/experience-observability/dashboard")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["total_experiences_tracked"] >= 5
        assert data["total_recalls"] >= 100
        assert data["overall_success_rate"] >= 0.8
        assert data["plugin_config"]["enabled"] is True


@pytest.mark.asyncio
async def test_get_trace_evidence_api(test_app: FastAPI) -> None:
    """Validate retrieving originating session evidence trace via REST API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Existing session trace
        res = await client.get("/api/memory/experience-observability/traces/sess_release_incident_09")
        assert res.status_code == 200
        data = res.json()
        assert data["session_id"] == "sess_release_incident_09"
        assert len(data["key_evidence_snippets"]) >= 2
        assert "DevOpsEngineer" in data["agent_role"]

        # Non-existent session trace -> 404
        res_404 = await client.get("/api/memory/experience-observability/traces/unknown_session_xyz")
        assert res_404.status_code == 404


@pytest.mark.asyncio
async def test_record_effect_event_api(test_app: FastAPI) -> None:
    """Validate recording a task outcome effect via REST API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_eff = await client.post(
            "/api/memory/experience-observability/record-effect",
            json={"entry_id": "proc_git_push_safe", "is_success": True, "is_dispute": False},
        )
        assert res_eff.status_code == 200
        data_eff = res_eff.json()
        assert data_eff["entry_id"] == "proc_git_push_safe"
        assert data_eff["effect_status"] == "effective"
        assert data_eff["success_rate"] >= 0.9


@pytest.mark.asyncio
async def test_plugin_config_update_api(test_app: FastAPI) -> None:
    """Validate updating host plugin configuration via REST API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Switch to MCP and Cursor host
        res_post = await client.post(
            "/api/memory/experience-observability/config",
            json={
                "active_channel": "mcp",
                "monitored_host": "cursor",
                "auto_warmup": False,
            },
        )
        assert res_post.status_code == 200
        updated = res_post.json()
        assert updated["active_channel"] == "mcp"
        assert updated["monitored_host"] == "cursor"
        assert updated["auto_warmup"] is False
