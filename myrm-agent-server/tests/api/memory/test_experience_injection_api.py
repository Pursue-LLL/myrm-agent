# [POS]: tests/api/memory/test_experience_injection_api.py
# [INPUT]: app.api.memory.experience_injection_router, isolated FastAPI app
# [OUTPUT]: Integration API tests for SkillLoadSubagentSpawnPreWriteExperienceInjectionSuite (Item 105)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.experience_injection_router import (
    router as experience_injection_router,
)
from app.services.memory.experience_injection_service import (
    ExperienceInjectionService,
    get_experience_injection_service,
)


@pytest.fixture
def isolated_service() -> ExperienceInjectionService:
    """Provides an isolated in-memory ExperienceInjectionService instance."""
    return ExperienceInjectionService()


@pytest.fixture
def test_app(isolated_service: ExperienceInjectionService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(experience_injection_router, prefix="/api/memory")
    app.dependency_overrides[get_experience_injection_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_skill_load_experience_injection_api(test_app: FastAPI) -> None:
    """Validate skill-load experience injection via REST API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "skill_name": "git_safe_push",
            "skill_content": "# Git Release Skill\nStep 1: Check diff\nStep 2: Push",
            "agent_id": "test-agent-01",
        }
        res = await client.post("/api/memory/experience-injection/skill-load", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["skill_name"] == "git_safe_push"
        assert data["status"] == "injected"
        assert data["injected_count"] >= 1
        assert "SafeGitBranchPushGuard" in data["enriched_content"]
        assert "Never git push -f" in data["enriched_content"]


@pytest.mark.asyncio
async def test_subagent_spawn_experience_injection_api(test_app: FastAPI) -> None:
    """Validate subagent spawn prompt enrichment via REST API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "subagent_role": "WorkerAgent",
            "task_prompt": "Execute database index migration subtask asynchronously.",
            "agent_id": "test-agent-01",
        }
        res = await client.post("/api/memory/experience-injection/subagent-spawn", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["subagent_role"] == "WorkerAgent"
        assert data["status"] == "injected"
        assert data["injected_count"] >= 1
        assert "[EXPERIENCE CONTEXT FOR DELEGATED TASK]" in data["enriched_prompt"]
        assert "SubagentContextHygieneGuideline" in data["enriched_prompt"]


@pytest.mark.asyncio
async def test_pre_write_guard_and_turn_reset_api(test_app: FastAPI) -> None:
    """Validate mutating tool pre-write check, one-time rollback recommendation, and turn reset."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        req = {
            "tool_name": "write_file",
            "tool_args": {"target_path": "/workspace/credentials.json", "content": "secret"},
            "current_context": "Attempting to save credentials",
            "agent_id": "test-agent-01",
        }

        # 1. First pre-write call triggers injection & rollback recommendation
        res1 = await client.post("/api/memory/experience-injection/pre-write", json=req)
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["status"] == "injected"
        assert data1["rollback_required"] is True
        assert "[PRE-WRITE GUARD: IMMUTABLE BOUNDARIES" in data1["enriched_context"]
        assert "credentials.json" in data1["enriched_context"]

        # 2. Second pre-write call in the same turn is skipped to avoid loop
        res2 = await client.post("/api/memory/experience-injection/pre-write", json=req)
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["status"] == "skipped_already_injected"
        assert data2["rollback_required"] is False

        # 3. Reset turn state
        res_reset = await client.post("/api/memory/experience-injection/reset-turn")
        assert res_reset.status_code == 200
        assert res_reset.json()["status"] == "ok"
