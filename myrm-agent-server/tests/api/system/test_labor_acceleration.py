"""[INPUT]
- httpx, ASGITransport
- app.api.system.labor_acceleration_api::router

[OUTPUT]
- Pytest test cases verifying white-collar labor acceleration telemetry, task equivalency breakdown, and monthly productivity ROI dashboard APIs.

[POS]
tests/api/system/test_labor_acceleration.py — 劳务效能加速度量化与生产力 ROI API 单元测试。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.system.labor_acceleration_api import router as labor_acceleration_router

test_app = FastAPI()
test_app.include_router(labor_acceleration_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_task_labor_acceleration(async_client: httpx.AsyncClient) -> None:
    task_id = "task-hermes-labor-888"
    resp = await async_client.get(f"/api/v1/system/labor-acceleration/{task_id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["task_id"] == task_id
    assert data["task_elapsed_seconds"] == 45.0
    assert data["total_hours_saved"] > 1.0
    assert data["acceleration_factor"] > 90.0  # 约 98.6x
    assert data["estimated_saved_value_usd"] > 40.0
    assert data["roi_ratio"] > 500.0
    assert len(data["breakdown"]) == 3


@pytest.mark.asyncio
async def test_calculate_labor_acceleration_post(async_client: httpx.AsyncClient) -> None:
    payload = {
        "task_id": "task-custom-calc-001",
        "task_elapsed_seconds": 60.0,
        "action_counts": {
            "web_research": 5,        # 5 * 0.10 = 0.5h
            "code_execution": 3,      # 3 * 0.3333 = 1.0h
            "doc_extraction": 2,      # 2 * 0.25 = 0.5h
        },
        "compute_cost_usd": 0.10,
        "hourly_rate_usd": 40.0,
    }
    resp = await async_client.post("/api/v1/system/labor-acceleration/calculate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["task_id"] == "task-custom-calc-001"
    # 总工时 ≈ 0.5 + 1.0 + 0.5 = 2.0 小时
    assert 1.99 < data["total_hours_saved"] < 2.01
    # 加速倍率: (2.0 * 3600) / 60 = 120x
    assert 118.0 < data["acceleration_factor"] < 122.0
    # 商业价值: 2.0 * $40 = $80
    assert 79.0 < data["estimated_saved_value_usd"] < 81.0
    # ROI: 80 / 0.10 = 800x
    assert 790.0 < data["roi_ratio"] < 810.0


@pytest.mark.asyncio
async def test_get_monthly_productivity_summary(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.get("/api/v1/system/labor-acceleration/monthly-summary")
    assert resp.status_code == 200
    data = resp.json()

    assert "month" in data
    assert data["total_tasks_automated"] >= 100
    assert data["total_hours_saved"] >= 50.0
    assert data["total_saved_value_usd"] > 1000.0
    assert data["overall_roi_ratio"] > 50.0
    assert len(data["top_saving_categories"]) == 3
