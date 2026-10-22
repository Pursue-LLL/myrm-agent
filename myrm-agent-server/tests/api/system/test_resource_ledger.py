"""[INPUT]
- httpx, ASGITransport
- app.api.system.resource_ledger_api::router

[OUTPUT]
- Pytest test cases verifying hybrid resource ledger and budget circuit breaker HTTP APIs.

[POS]
tests/api/system/test_resource_ledger.py — 物理硬件占用与认知 Token 混合对账单 API 单元测试。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.system.resource_ledger_api import router as resource_ledger_router

test_app = FastAPI()
test_app.include_router(resource_ledger_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_task_resource_ledger(async_client: httpx.AsyncClient) -> None:
    task_id = "task-cloud-run-888"
    resp = await async_client.get(f"/api/v1/system/resource-ledger/{task_id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["task_id"] == task_id
    assert "hardware" in data
    assert "cognitive" in data
    assert data["hardware"]["execution_seconds"] == 660.0
    assert data["hardware"]["hardware_credits"] > 0.0
    assert data["cognitive"]["cognitive_credits"] > 0.0
    assert data["total_credits"] > 0.0
    assert data["estimated_cost_usd"] > 0.0
    assert data["is_budget_exceeded"] is False


@pytest.mark.asyncio
async def test_estimate_resource_ledger_normal(async_client: httpx.AsyncClient) -> None:
    payload = {
        "task_id": "task-estimate-001",
        "execution_seconds": 300.0,
        "cpu_cores": 2.0,
        "memory_gb": 4.0,
        "volume_read_mb": 50.0,
        "volume_write_mb": 20.0,
        "model_name": "deepseek-v3",
        "prompt_tokens": 15000,
        "completion_tokens": 3000,
        "cached_prompt_tokens": 5000,
        "max_execution_seconds": 600.0,
        "max_total_tokens": 50000,
        "max_total_credits": 100.0,
    }
    resp = await async_client.post("/api/v1/system/resource-ledger/estimate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["task_id"] == "task-estimate-001"
    assert data["hardware"]["execution_seconds"] == 300.0
    assert data["cognitive"]["prompt_tokens"] == 15000
    assert data["is_budget_exceeded"] is False
    assert data["total_credits"] > 0.0


@pytest.mark.asyncio
async def test_estimate_resource_ledger_budget_exceeded(async_client: httpx.AsyncClient) -> None:
    # 模拟沙箱超时触发熔断
    payload = {
        "task_id": "task-estimate-overtime",
        "execution_seconds": 1200.0,
        "max_execution_seconds": 600.0,
    }
    resp = await async_client.post("/api/v1/system/resource-ledger/estimate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["is_budget_exceeded"] is True
    assert "物理沙箱运行时间" in data["budget_exceeded_reason"]


@pytest.mark.asyncio
async def test_estimate_resource_ledger_validation_error(async_client: httpx.AsyncClient) -> None:
    # 传入非法的 CPU 核数 (< 0.5)
    payload = {
        "task_id": "task-invalid",
        "cpu_cores": 0.1,
    }
    resp = await async_client.post("/api/v1/system/resource-ledger/estimate", json=payload)
    assert resp.status_code == 422
