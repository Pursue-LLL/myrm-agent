"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.token_economics_api::router

[OUTPUT]:
- Pytest test cases verifying token economics evaluation, cache ROI calculation, unit cost drift auditing, and runaway cost circuit breakers.

[POS]:
tests/api/system/test_token_economics_api.py — 长任务 Token 经济学、99% 缓存节流与账单防刺客 API 单元测试。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.token_economics_api import router as token_economics_router

test_app = FastAPI()
test_app.include_router(token_economics_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_evaluate_token_economics(async_client: httpx.AsyncClient) -> None:
    # 模拟 100k prompt，其中 99k 命中缓存 (99% 缓存命中)
    payload = {
        "task_id": "task-mimo-99",
        "model_name": "deepseek-chat",
        "task_category": "code_architecture",
        "total_prompt_tokens": 100_000,
        "cached_prompt_tokens": 99_000,
        "completion_tokens": 3_000,
        "execution_duration_seconds": 90.0,
    }
    resp = await async_client.post("/api/v1/system/token-economics/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["task_id"] == "task-mimo-99"
    assert data["cache_hit_rate_pct"] == 99.0
    assert data["baseline_cost_rmb"] > data["actual_cost_rmb"]
    assert data["saved_amount_rmb"] > 0.0
    assert data["saved_percentage"] > 80.0
    assert data["burn_rate_rmb_per_minute"] > 0.0


@pytest.mark.asyncio
async def test_audit_cost_drift_api(async_client: httpx.AsyncClient) -> None:
    # 1. 建立基线样本
    for _ in range(3):
        base_resp = await async_client.post(
            "/api/v1/system/token-economics/drift-audit",
            json={
                "model_name": "deepseek-chat",
                "task_category": "data_pipeline",
                "total_tokens": 20_000,
                "actual_cost_rmb": 0.05,
                "cache_hit_rate_pct": 98.0,
                "is_routed_fallback": False,
            },
        )
        assert base_resp.status_code == 200
        assert base_resp.json()["is_significant_drift"] is False

    # 2. 模拟缓存击穿劣化 (命中率跌至 10%)
    bust_resp = await async_client.post(
        "/api/v1/system/token-economics/drift-audit",
        json={
            "model_name": "deepseek-chat",
            "task_category": "data_pipeline",
            "total_tokens": 20_000,
            "actual_cost_rmb": 0.25,
            "cache_hit_rate_pct": 10.0,
            "is_routed_fallback": False,
        },
    )
    assert bust_resp.status_code == 200
    bust_data = bust_resp.json()
    assert bust_data["is_significant_drift"] is True
    assert bust_data["reason"] == "CACHE_HIT_DEGRADED"
    assert "缓存击穿劣化" in bust_data["explanation"]


@pytest.mark.asyncio
async def test_evaluate_budget_guard_api(async_client: httpx.AsyncClient) -> None:
    custom_policy = {
        "max_allowed_cost_rmb": 10.0,
        "soft_warning_threshold_rmb": 7.0,
        "max_allowed_tokens": 100_000,
        "max_burn_rate_rmb_per_minute": 3.0,
    }

    # 1. 正常状态
    resp_ok = await async_client.post(
        "/api/v1/system/token-economics/guard-check",
        json={
            "current_cost_rmb": 3.0,
            "current_tokens": 20_000,
            "duration_seconds": 120.0,
            "policy": custom_policy,
        },
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["status"] == "OK"
    assert resp_ok.json()["is_paused"] is False

    # 2. 触发软预警 (开销 7.5 元)
    resp_warn = await async_client.post(
        "/api/v1/system/token-economics/guard-check",
        json={
            "current_cost_rmb": 7.5,
            "current_tokens": 50_000,
            "duration_seconds": 180.0,
            "policy": custom_policy,
        },
    )
    assert resp_warn.status_code == 200
    assert resp_warn.json()["status"] == "SOFT_WARNING"
    assert resp_warn.json()["is_paused"] is False

    # 3. 触发硬预算熔断 (开销 12.0 元)
    resp_trip = await async_client.post(
        "/api/v1/system/token-economics/guard-check",
        json={
            "current_cost_rmb": 12.0,
            "current_tokens": 60_000,
            "duration_seconds": 240.0,
            "policy": custom_policy,
        },
    )
    assert resp_trip.status_code == 200
    assert resp_trip.json()["status"] == "CIRCUIT_BREAKER_TRIPPED"
    assert resp_trip.json()["is_paused"] is True
    assert "熔断" in resp_trip.json()["reason"]
