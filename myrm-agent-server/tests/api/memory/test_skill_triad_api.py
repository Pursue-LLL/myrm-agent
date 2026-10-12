"""Integration and unit tests for Memory Skill Triad and Physical Scope Isolation API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.skill_triad_router import router as skill_triad_router


@pytest.fixture
def test_app() -> FastAPI:
    """Create lightweight test FastAPI application hosting the skill triad router."""
    api_app = FastAPI()
    api_app.include_router(skill_triad_router, prefix="/api/memory")
    return api_app


@pytest.mark.asyncio
async def test_skill_triad_health(test_app: FastAPI) -> None:
    """Test health check probe endpoint for skill triad subsystem."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.get("/api/memory/skill-triad/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["module"] == "skill_triad"
        assert data["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_resolve_and_delete_scope_partition(test_app: FastAPI) -> None:
    """Test deterministic scope resolution and atomic physical deletion."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        resolve_payload = {
            "coordinates": {
                "tenant_id": "tenant-alpha",
                "workspace_id": "ws-production",
                "agent_id": "researcher-01",
                "session_id": "sess-999",
            }
        }
        res_response = await client.post(
            "/api/memory/skill-triad/scope/resolve",
            json=resolve_payload,
        )
        assert res_response.status_code == 200
        res_data = res_response.json()
        assert res_data["is_isolated"] is True
        assert len(res_data["namespace_hash"]) == 32
        db_path = Path(res_data["sqlite_path"])
        assert db_path.name == "memory.sqlite"
        assert Path(res_data["partition_dir"]).exists()

        # Create dummy sqlite file to verify deletion
        db_path.touch()
        assert db_path.exists()

        del_payload = {
            "coordinates": {
                "tenant_id": "tenant-alpha",
                "workspace_id": "ws-production",
                "agent_id": "researcher-01",
                "session_id": "sess-999",
            }
        }
        del_response = await client.post(
            "/api/memory/skill-triad/scope/delete",
            json=del_payload,
        )
        assert del_response.status_code == 200
        del_data = del_response.json()
        assert del_data["deleted"] is True
        assert not db_path.parent.exists()


@pytest.mark.asyncio
async def test_assess_providers_degraded_and_healthy(test_app: FastAPI) -> None:
    """Test provider assessment returns degraded diagnostics without blowing up."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # 1. Healthy assessment
        healthy_req = {
            "configured_providers": {
                "embedder": "builtin",
                "llm": "deterministic_rules",
            },
            "strict_mode": False,
        }
        res_healthy = await client.post(
            "/api/memory/skill-triad/provider/assess",
            json=healthy_req,
        )
        assert res_healthy.status_code == 200
        data_healthy = res_healthy.json()
        assert data_healthy["overall_status"] == "healthy"
        assert len(data_healthy["providers"]) == 2
        for provider_info in data_healthy["providers"]:
            assert provider_info["is_degraded"] is False

        # 2. Degraded assessment (missing/unsupported vendor falls back to local lexical)
        degraded_req = {
            "configured_providers": {
                "embedder": "unavailable-embedder-99",
            },
            "strict_mode": False,
        }
        res_degraded = await client.post(
            "/api/memory/skill-triad/provider/assess",
            json=degraded_req,
        )
        assert res_degraded.status_code == 200
        data_degraded = res_degraded.json()
        assert data_degraded["overall_status"] == "degraded_lexical_fallback"
        assert len(data_degraded["providers"]) == 1
        assert data_degraded["providers"][0]["is_degraded"] is True
        assert "degraded visibly" in data_degraded["providers"][0]["degradation_reason"].lower()


@pytest.mark.asyncio
async def test_format_cli_envelope_success_and_error(test_app: FastAPI) -> None:
    """Test formatting JSON envelope for machine agents with auto-confirmation flag."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # Success case
        ok_payload = {
            "command": "memory.recall",
            "scope": {
                "tenant_id": "tenant-beta",
                "workspace_id": "ws-dev",
                "agent_id": "agent-007",
                "session_id": "sess-123",
            },
            "payload": {"recalled_count": "5", "top_match": "user preference"},
            "agent_mode": True,
        }
        res_ok = await client.post(
            "/api/memory/skill-triad/cli/envelope",
            json=ok_payload,
        )
        assert res_ok.status_code == 200
        data_ok = res_ok.json()
        assert data_ok["status"] == "success"
        assert data_ok["exit_code"] == 0
        assert data_ok["auto_confirmed"] is True
        assert data_ok["command"] == "memory.recall"
        assert data_ok["payload"]["recalled_count"] == "5"


@pytest.mark.asyncio
async def test_pipeline_survey_validation(test_app: FastAPI) -> None:
    """Test 4-question pre-integration repository survey validation."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # Full answers
        full_survey = {
            "finding": {
                "message_assembly_site": "agent/prompt/builder.py:42",
                "identity_binding": "user_id + workspace_id header",
                "installed_provider": "openai + sqlite-vec",
                "write_hook_seam": "agent/loop.py:run_turn_after_flush",
                "is_ready_for_wiring": True,
            }
        }
        res_full = await client.post(
            "/api/memory/skill-triad/pipeline/survey",
            json=full_survey,
        )
        assert res_full.status_code == 200
        data_full = res_full.json()
        assert data_full["is_valid"] is True
        assert len(data_full["issues"]) == 0

        # Partial answers
        partial_survey = {
            "finding": {
                "message_assembly_site": "",
                "identity_binding": "user_id",
                "installed_provider": "",
                "write_hook_seam": "",
                "is_ready_for_wiring": False,
            }
        }
        res_part = await client.post(
            "/api/memory/skill-triad/pipeline/survey",
            json=partial_survey,
        )
        assert res_part.status_code == 200
        data_part = res_part.json()
        assert data_part["is_valid"] is False
        assert len(data_part["issues"]) >= 2


@pytest.mark.asyncio
async def test_pipeline_verify_seams(test_app: FastAPI) -> None:
    """Test verifying read/write integration seams and roundtrip test flag."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # Verified case
        verified_req = {
            "read_seam_configured": True,
            "write_seam_configured": True,
            "token_budget": 500,
            "roundtrip_test_passed": True,
        }
        res_v = await client.post(
            "/api/memory/skill-triad/pipeline/verify",
            json=verified_req,
        )
        assert res_v.status_code == 200
        data_v = res_v.json()
        assert data_v["is_verified"] is True
        assert "successfully verified" in data_v["message"]

        # Deficient case
        deficient_req = {
            "read_seam_configured": False,
            "write_seam_configured": True,
            "token_budget": 500,
            "roundtrip_test_passed": False,
        }
        res_d = await client.post(
            "/api/memory/skill-triad/pipeline/verify",
            json=deficient_req,
        )
        assert res_d.status_code == 200
        data_d = res_d.json()
        assert data_d["is_verified"] is False
        assert "Read seam unconfigured" in data_d["message"]
