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
async def test_list_and_filter_metrics_api(test_app: FastAPI) -> None:
    """Validate listing and filtering experience metrics by channel and status."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Full list
        res = await client.get("/api/memory/experience-observability/metrics")
        assert res.status_code == 200
        items = res.json()
        assert len(items) >= 5
        entry_ids = [m["entry_id"] for m in items]
        assert "proc_git_push_safe" in entry_ids
        assert "RET-EXC-01" in entry_ids

        # 2. Filter by channel
        res_mcp = await client.get("/api/memory/experience-observability/metrics?channel=mcp")
        assert res_mcp.status_code == 200
        items_mcp = res_mcp.json()
        assert any(m["entry_id"] == "proc_db_index_ddl" for m in items_mcp)

        # 3. Single metric lookup
        res_single = await client.get("/api/memory/experience-observability/metrics/proc_git_push_safe")
        assert res_single.status_code == 200
        metric = res_single.json()
        assert metric["name"] == "SafeGitBranchPushGuard"

        # 4. Single metric not found -> 404
        res_404 = await client.get("/api/memory/experience-observability/metrics/non_existent_exp")
        assert res_404.status_code == 404


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
async def test_record_recall_and_effect_events_api(test_app: FastAPI) -> None:
    """Validate recording recall hits and task outcome effects via REST API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Record recall
        res_rec = await client.post(
            "/api/memory/experience-observability/record-recall",
            json={"entry_id": "proc_git_push_safe", "channel": "mcp"},
        )
        assert res_rec.status_code == 200
        data_rec = res_rec.json()
        assert data_rec["access_channel"] == "mcp"

        # 2. Record effect (success)
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
async def test_plugin_config_api(test_app: FastAPI) -> None:
    """Validate getting and updating host plugin configuration via REST API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET config
        res_get = await client.get("/api/memory/experience-observability/config")
        assert res_get.status_code == 200
        cfg = res_get.json()
        assert cfg["enabled"] is True
        assert cfg["active_channel"] == "plugin"

        # POST update config: switch to MCP and Cursor host
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
