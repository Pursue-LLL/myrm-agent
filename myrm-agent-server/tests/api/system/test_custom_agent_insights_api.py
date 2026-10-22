"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.custom_agent_insights_api::router

[OUTPUT]:
- Pytest verification for Custom Agent Insights and Operational Observability API endpoints.

[POS]:
tests/api/system/test_custom_agent_insights_api.py — 自定义智能体洞察与运营可观测性 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.custom_agent_insights_api import router as insights_router

test_app = FastAPI()
test_app.include_router(insights_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_custom_agent_insights_api_flow(async_client: httpx.AsyncClient) -> None:
    # 1. Reset all tracker metrics
    reset_resp = await async_client.post("/api/v1/system/custom-agent-insights/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"ok": True}

    # 2. Check initial clean snapshot for agent-alpha
    init_resp = await async_client.get(
        "/api/v1/system/custom-agent-insights/insights",
        params={"agent_id": "agent-alpha", "window_days": 7},
    )
    assert init_resp.status_code == 200
    init_data = init_resp.json()
    assert init_data["agent_id"] == "agent-alpha"
    assert init_data["total_interactions"] == 0
    assert init_data["total_tokens_consumed"] == 0
    assert init_data["intent_clusters"] == []
    assert init_data["skill_funnel"] == []
    assert init_data["hitl_metrics"]["total_tasks"] == 0
    assert init_data["hitl_metrics"]["token_roi_ratio"] == 1.0

    # 3. Record interaction events
    r1 = await async_client.post(
        "/api/v1/system/custom-agent-insights/record-interaction",
        json={
            "agent_id": "agent-alpha",
            "intent_category": "database_optimization",
            "utterance": "Help me optimize slow queries",
            "tokens": 1500,
        },
    )
    assert r1.status_code == 200
    assert r1.json() == {"ok": True}

    r2 = await async_client.post(
        "/api/v1/system/custom-agent-insights/record-interaction",
        json={
            "agent_id": "agent-alpha",
            "intent_category": "database_optimization",
            "utterance": "Add missing index on orders table",
            "tokens": 2000,
        },
    )
    assert r2.status_code == 200

    r3 = await async_client.post(
        "/api/v1/system/custom-agent-insights/record-interaction",
        json={
            "agent_id": "agent-alpha",
            "intent_category": "architecture_review",
            "utterance": "Review ADR for cache invalidation",
            "tokens": 3000,
        },
    )
    assert r3.status_code == 200

    # 4. Record skill execution events
    s1 = await async_client.post(
        "/api/v1/system/custom-agent-insights/record-skill",
        json={
            "agent_id": "agent-alpha",
            "skill_name": "sql_explain_analyzer",
            "latency_ms": 120.5,
            "status": "SUCCESS",
            "error_reason": "",
        },
    )
    assert s1.status_code == 200

    s2 = await async_client.post(
        "/api/v1/system/custom-agent-insights/record-skill",
        json={
            "agent_id": "agent-alpha",
            "skill_name": "sql_explain_analyzer",
            "latency_ms": 180.0,
            "status": "FAILURE",
            "error_reason": "ConnectionTimeout",
        },
    )
    assert s2.status_code == 200

    s3 = await async_client.post(
        "/api/v1/system/custom-agent-insights/record-skill",
        json={
            "agent_id": "agent-alpha",
            "skill_name": "git_commit_validator",
            "latency_ms": 45.0,
            "status": "SUCCESS",
            "error_reason": "",
        },
    )
    assert s3.status_code == 200

    # 5. Record HITL friction and deliverables
    h1 = await async_client.post(
        "/api/v1/system/custom-agent-insights/record-hitl",
        json={
            "agent_id": "agent-alpha",
            "intercepted": True,
            "wait_seconds": 42.0,
            "deliverables_count": 2,
            "tokens_consumed": 5000,
        },
    )
    assert h1.status_code == 200

    h2 = await async_client.post(
        "/api/v1/system/custom-agent-insights/record-hitl",
        json={
            "agent_id": "agent-alpha",
            "intercepted": False,
            "wait_seconds": 0.0,
            "deliverables_count": 3,
            "tokens_consumed": 4000,
        },
    )
    assert h2.status_code == 200

    # 6. Retrieve and assert operational insights snapshot
    snapshot_resp = await async_client.get(
        "/api/v1/system/custom-agent-insights/insights",
        params={"agent_id": "agent-alpha", "window_days": 7},
    )
    assert snapshot_resp.status_code == 200
    data = snapshot_resp.json()

    assert data["agent_id"] == "agent-alpha"
    assert data["total_interactions"] == 3
    assert data["total_tokens_consumed"] == 6500

    # Intent clusters check
    clusters = data["intent_clusters"]
    assert len(clusters) == 2
    assert clusters[0]["intent_category"] == "database_optimization"
    assert clusters[0]["request_count"] == 2
    assert clusters[0]["share_pct"] == 66.7
    assert clusters[1]["intent_category"] == "architecture_review"
    assert clusters[1]["request_count"] == 1
    assert clusters[1]["share_pct"] == 33.3

    # Skill funnel check
    funnel = data["skill_funnel"]
    assert len(funnel) == 2
    sql_metric = next(s for s in funnel if s["skill_name"] == "sql_explain_analyzer")
    assert sql_metric["total_calls"] == 2
    assert sql_metric["success_rate_pct"] == 50.0
    assert "ConnectionTimeout" in sql_metric["top_error_reasons"]

    git_metric = next(s for s in funnel if s["skill_name"] == "git_commit_validator")
    assert git_metric["total_calls"] == 1
    assert git_metric["success_rate_pct"] == 100.0

    # HITL metrics check
    hitl = data["hitl_metrics"]
    assert hitl["total_tasks"] == 2
    assert hitl["hitl_intercepted_tasks"] == 1
    assert hitl["hitl_interception_rate_pct"] == 50.0
    assert hitl["avg_approval_wait_seconds"] == 42.0
    assert hitl["token_roi_ratio"] > 0.0

    # 7. Test agent-specific reset
    r_spec = await async_client.post(
        "/api/v1/system/custom-agent-insights/reset",
        json={"agent_id": "agent-alpha"},
    )
    assert r_spec.status_code == 200
    cleared_resp = await async_client.get(
        "/api/v1/system/custom-agent-insights/insights",
        params={"agent_id": "agent-alpha"},
    )
    assert cleared_resp.json()["total_interactions"] == 0
