"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.delivery_budget_api::router

[OUTPUT]:
- Pytest test cases verifying cumulative delivery budget accounting, unmetered usage imputation, and hard pause fuses.

[POS]:
tests/api/system/test_delivery_budget_api.py — 整轮交付累计预算与未知用量审计 API 单元测试。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.delivery_budget_api import router as delivery_budget_router

test_app = FastAPI()
test_app.include_router(delivery_budget_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_record_trial_and_get_cumulative_ledger(
    async_client: httpx.AsyncClient,
) -> None:
    delivery_id = "deliv-server-test-01"

    # 1. 记录第一个 Planner 尝试
    payload1 = {
        "delivery_id": delivery_id,
        "trial_id": "trial-001",
        "agent_id": "planner-01",
        "agent_role": "planner",
        "attempt_index": 1,
        "step_name": "系统架构规划与模块拆解",
        "prompt_tokens": 3000,
        "completion_tokens": 1000,
        "cost_usd": 0.025,
        "latency_ms": 1500.0,
        "is_unmetered": False,
        "status": "success",
    }
    resp1 = await async_client.post(
        "/api/v1/system/delivery-budget/record-trial", json=payload1
    )
    assert resp1.status_code == 200
    data1 = resp1.json()

    assert data1["delivery_id"] == delivery_id
    assert data1["total_trials_count"] == 1
    assert data1["unmetered_trials_count"] == 0
    assert data1["total_metered_tokens"] == 4000
    assert data1["total_effective_tokens"] == 4000
    assert data1["total_metered_cost_usd"] == 0.025

    # 2. 查询该交付账本
    get_resp = await async_client.get(
        f"/api/v1/system/delivery-budget/{delivery_id}"
    )
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["delivery_id"] == delivery_id
    assert len(get_data["trials"]) == 1
    assert get_data["trials"][0]["trial_id"] == "trial-001"


@pytest.mark.asyncio
async def test_unmetered_usage_conservative_imputation(
    async_client: httpx.AsyncClient,
) -> None:
    delivery_id = "deliv-server-test-unmetered"

    # 记录显式未计量调用 (如网络抖动 Provider 未回传 usage)
    payload_unmetered = {
        "delivery_id": delivery_id,
        "trial_id": "trial-unmetered-01",
        "agent_id": "worker-crawler",
        "agent_role": "worker",
        "attempt_index": 1,
        "step_name": "多源网页流式抓取与抽取",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cost_usd": 0.0,
        "latency_ms": 3200.0,
        "is_unmetered": True,
        "unmetered_status": "UNMETERED_TIMEOUT",
        "custom_imputed_prompt_tokens": 2000,
        "custom_imputed_completion_tokens": 800,
        "custom_imputed_cost_usd": 0.008,
        "status": "timeout",
    }

    resp = await async_client.post(
        "/api/v1/system/delivery-budget/record-trial", json=payload_unmetered
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["unmetered_trials_count"] == 1
    assert data["total_metered_tokens"] == 0
    assert data["total_imputed_tokens"] == 2800  # 2000 + 800
    assert data["total_effective_tokens"] == 2800
    assert data["total_imputed_cost_usd"] == 0.008
    assert data["total_effective_cost_usd"] == 0.008

    trial = data["trials"][0]
    assert trial["is_unmetered"] is True
    assert trial["unmetered_status"] == "UNMETERED_TIMEOUT"
    assert trial["effective_tokens"] == 2800


@pytest.mark.asyncio
async def test_hard_budget_fuse_and_adjustment(
    async_client: httpx.AsyncClient,
) -> None:
    delivery_id = "deliv-server-test-fuse"

    # 初始记录并消耗 12000 tokens，初始预算设定为 10000 tokens (120% 超标触发 EXCEEDED_PAUSED_100)
    payload = {
        "delivery_id": delivery_id,
        "trial_id": "trial-fuse-1",
        "agent_id": "coder-01",
        "agent_role": "coder",
        "attempt_index": 1,
        "step_name": "核心业务链路实现",
        "prompt_tokens": 8000,
        "completion_tokens": 4000,
        "cost_usd": 0.08,
        "latency_ms": 2000.0,
        "budget_tokens_limit": 10000,
        "budget_cost_limit_usd": 0.20,
    }
    resp1 = await async_client.post(
        "/api/v1/system/delivery-budget/record-trial", json=payload
    )
    assert resp1.status_code == 200
    data_paused = resp1.json()
    assert data_paused["gate_verdict"] == "EXCEEDED_PAUSED_100"
    assert data_paused["is_paused"] is True
    assert "触发保护性熔断挂起" in (data_paused["pause_reason"] or "")

    # 人工追加 20000 tokens 预算并解除暂停 (总限额变为 30000 tokens，使用率 12000/30000 = 40%)
    resume_resp = await async_client.post(
        f"/api/v1/system/delivery-budget/{delivery_id}/adjust-budget",
        json={"additional_tokens": 20000, "additional_cost_usd": 0.20, "force_unpause": True},
    )
    assert resume_resp.status_code == 200
    data_resumed = resume_resp.json()
    assert data_resumed["is_paused"] is False
    assert data_resumed["gate_verdict"] == "NORMAL"
