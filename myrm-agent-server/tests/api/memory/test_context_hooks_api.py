"""Integration tests for Pluggable Context Hook Pipeline & Memory Injection API.

[POS]
Integration tests verifying lifecycle context hook interception, custom agent
dual-layer memory weaving, egress credential sanitization, and pipeline telemetry.

[INPUT]
- fastapi, httpx.AsyncClient, pytest
- app.api.memory.context_hooks_router (router)
- app.services.memory.context_hooks.provider (reset_context_hook_suite)

[OUTPUT]
- Test functions covering context hook API endpoints.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.context_hooks_router import (
    router as context_hooks_router,
)
from app.services.memory.context_hooks.provider import (
    reset_context_hook_suite,
)


@pytest.fixture(autouse=True)
def reset_suite_before_test() -> None:
    """Reset suite before each test to guarantee fresh default state."""
    reset_context_hook_suite()


@pytest.fixture
def test_app() -> FastAPI:
    """Create FastAPI test application with context hooks router."""
    api_app = FastAPI()
    api_app.include_router(context_hooks_router, prefix="/api/memory")
    return api_app


@pytest.mark.asyncio
async def test_intercept_stage_before_agent_start(test_app: FastAPI) -> None:
    """Verify executing before_agent_start stage triggers environment injection."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/memory/context-hooks/pipeline/intercept",
            json={
                "stage": "before_agent_start",
                "envelope": {
                    "session_id": "sess_env_01",
                    "agent_id": "code_refactorer",
                    "system_prompt": "Refactor python module",
                    "injected_memories": [],
                    "metadata": {},
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert not data["envelope"]["is_blocked"]
        assert data["envelope"]["metadata"].get("runtime_fence") == "sandbox_hardened"
        assert len(data["reports"]) >= 1
        assert data["reports"][0]["hook_id"] == "builtin_env_guard"


@pytest.mark.asyncio
async def test_weave_memory_endpoint(test_app: FastAPI) -> None:
    """Verify dual-layer memory weaving endpoint filters foreign agent memories."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/memory/context-hooks/weave-memory",
            json={
                "agent_id": "arch_reviewer",
                "private_fragments": [
                    {
                        "fragment_id": "pf_own",
                        "layer": "private_agent",
                        "content": "专属偏好：重点审查模块间循环依赖与包分层契约",
                        "weight": 2.0,
                        "tags": ["arch"],
                        "agent_id": "arch_reviewer",
                    },
                    {
                        "fragment_id": "pf_other",
                        "layer": "private_agent",
                        "content": "异构智能体记忆：专心调优前端 TailwindCSS 样式",
                        "weight": 3.0,
                        "tags": ["css"],
                        "agent_id": "ui_designer",  # Must be ignored
                    },
                ],
                "shared_fragments": [
                    {
                        "fragment_id": "sf_global",
                        "layer": "shared_global",
                        "content": "全局公理：单文件不超过 350 行，严禁 Any 类型",
                        "weight": 1.5,
                        "tags": ["policy"],
                    }
                ],
                "max_token_budget": 800,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["private_count"] == 1
        assert data["shared_count"] == 1
        assert "重点审查模块间循环依赖" in data["woven_block"]
        assert "TailwindCSS" not in data["woven_block"]
        assert "严禁 Any 类型" in data["woven_block"]


@pytest.mark.asyncio
async def test_full_lifecycle_pipeline_and_egress_sanitization(test_app: FastAPI) -> None:
    """Verify full lifecycle execution weaves memories and sanitizes leaked credentials."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/memory/context-hooks/pipeline/full-lifecycle",
            json={
                "envelope": {
                    "session_id": "sess_full_01",
                    "agent_id": "devops_sec",
                    "system_prompt": "Deploy cluster with token: ghp_123456789012345678901234567890",
                    "injected_memories": [],
                    "metadata": {},
                },
                "memory_payload": {
                    "agent_id": "devops_sec",
                    "private_fragments": [
                        {
                            "fragment_id": "priv_k8s",
                            "layer": "private_agent",
                            "content": "强制使用 Helm Chart 生产级模板部署",
                            "weight": 2.0,
                            "agent_id": "devops_sec",
                        }
                    ],
                    "shared_fragments": [],
                    "max_token_budget": 400,
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        env = data["envelope"]
        # Egress redaction
        assert "ghp_1234567890" not in env["system_prompt"]
        assert "[REDACTED_SECRET]" in env["system_prompt"]
        # Context enrichment
        assert "[Active Agent: devops_sec]" in env["system_prompt"]
        # Memory weaving injection
        assert len(env["injected_memories"]) == 1
        assert "强制使用 Helm Chart" in env["injected_memories"][0]
        # Reports across stages
        stage_reports = data["stage_reports"]
        assert "before_agent_start" in stage_reports
        assert "context_transform" in stage_reports
        assert "before_llm_request" in stage_reports


@pytest.mark.asyncio
async def test_list_stages_and_stats(test_app: FastAPI) -> None:
    """Verify listing registered hooks and retrieving stats."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # 1. List registered hooks
        list_resp = await client.get("/api/memory/context-hooks/stages")
        assert list_resp.status_code == 200
        hooks = list_resp.json()
        hook_ids = [h["hook_id"] for h in hooks]
        assert "builtin_env_guard" in hook_ids
        assert "builtin_egress_redactor" in hook_ids

        # 2. Retrieve stats
        stats_resp = await client.get("/api/memory/context-hooks/stats")
        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert stats["total_hooks"] >= 3
        assert stats["before_agent_start"] >= 1
        assert stats["before_llm_request"] >= 1
