"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.workflow_burn_api::router

[OUTPUT]:
- Pytest test cases verifying workflow token burn rate tracking, tiered budget ladder alerts, and dynamic budget adjustment APIs.

[POS]:
tests/api/system/test_workflow_burn.py — 海量并发 Agent 编排 Token 燃速与动态阶梯风控 API 单元测试。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.workflow_burn_api import router as workflow_burn_router

test_app = FastAPI()
test_app.include_router(workflow_burn_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_workflow_burn_status_initial(async_client: httpx.AsyncClient) -> None:
    wf_id = "wf-init-001"
    resp = await async_client.get(f"/api/v1/system/workflow-burn/{wf_id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["workflow_id"] == wf_id
    assert data["tokens_per_sec"] > 0
    assert data["total_cumulative_tokens"] > 0
    assert data["active_agent_count"] >= 1
    assert "verdict" in data
    assert data["verdict"]["tier"] in ("NORMAL", "TIER1_NOTICE", "TIER2_DEGRADED", "TIER3_SUSPENDED")


@pytest.mark.asyncio
async def test_record_checkpoint_and_throttle_verdict(async_client: httpx.AsyncClient) -> None:
    wf_id = "wf-batch-crawlers"
    budget_tokens = 100_000
    budget_cost = 5.0

    # Checkpoint 1: 30% consumption -> NORMAL
    p1 = {
        "workflow_id": wf_id,
        "cumulative_prompt_tokens": 20000,
        "cumulative_completion_tokens": 10000,
        "cumulative_cost_usd": 1.2,
        "active_agent_count": 64,
        "budget_tokens": budget_tokens,
        "budget_cost_usd": budget_cost,
        "agent_burn_distribution": {"agent-0": 15000, "agent-1": 15000},
        "timestamp": 100.0,
    }
    r1 = await async_client.post("/api/v1/system/workflow-burn/record-checkpoint", json=p1)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["verdict"]["tier"] == "NORMAL"
    assert d1["verdict"]["is_throttled"] is False

    # Checkpoint 2: 85% consumption at t=102s -> TIER2_DEGRADED
    p2 = {
        "workflow_id": wf_id,
        "cumulative_prompt_tokens": 55000,
        "cumulative_completion_tokens": 30000,  # total 85,000 = 85%
        "cumulative_cost_usd": 4.1,
        "active_agent_count": 64,
        "budget_tokens": budget_tokens,
        "budget_cost_usd": budget_cost,
        "agent_burn_distribution": {"agent-0": 45000, "agent-1": 40000},
        "timestamp": 102.0,
    }
    r2 = await async_client.post("/api/v1/system/workflow-burn/record-checkpoint", json=p2)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["verdict"]["tier"] == "TIER2_DEGRADED"
    assert d2["verdict"]["is_throttled"] is True
    assert d2["verdict"]["throttle_factor"] == 0.5
    assert d2["verdict"]["recommended_model_tier"] == "economy"
    # Rate: (85000 - 30000) / 2s = 27500 tokens/sec
    assert d2["tokens_per_sec"] == 27500.0


@pytest.mark.asyncio
async def test_adjust_budget_resumes_workflow(async_client: httpx.AsyncClient) -> None:
    wf_id = "wf-suspended-job"

    # Push to 100% suspended
    p = {
        "workflow_id": wf_id,
        "cumulative_prompt_tokens": 80000,
        "cumulative_completion_tokens": 25000,  # 105,000 tokens
        "cumulative_cost_usd": 5.5,
        "active_agent_count": 128,
        "budget_tokens": 100000,
        "budget_cost_usd": 5.0,
        "timestamp": 200.0,
    }
    await async_client.post("/api/v1/system/workflow-burn/record-checkpoint", json=p)

    status_resp = await async_client.get(f"/api/v1/system/workflow-burn/{wf_id}")
    assert status_resp.json()["verdict"]["tier"] == "TIER3_SUSPENDED"
    assert status_resp.json()["verdict"]["is_suspended"] is True

    # Adjust budget: add 100k tokens and 5 USD
    adjust_resp = await async_client.post(
        f"/api/v1/system/workflow-burn/{wf_id}/adjust-budget",
        json={"added_tokens": 100000, "added_cost_usd": 5.0},
    )
    assert adjust_resp.status_code == 200
    adj_data = adjust_resp.json()

    assert adj_data["budget_tokens"] == 200000
    # 105,000 / 200,000 = 52.5% -> TIER1_NOTICE, no longer suspended
    assert adj_data["verdict"]["is_suspended"] is False
    assert adj_data["verdict"]["tier"] == "TIER1_NOTICE"
