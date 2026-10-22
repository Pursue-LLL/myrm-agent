"""Unit tests for ROI and productivity analytics HTTP endpoints.

[INPUT]
- httpx, ASGITransport
- app.api.system.roi_analytics_api::router

[OUTPUT]
- Pytest test cases verifying dashboard metrics, out-of-the-box routines, and ad-hoc calculation.

[POS]
tests/api/system/test_roi_analytics_api.py - Unit test suite for Item 51 P0.
Strictly under 120 lines. Zero Any.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.system.roi_analytics_api import router as roi_analytics_router

test_app = FastAPI()
test_app.include_router(roi_analytics_router, prefix="/api/v1")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_roi_dashboard_default(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.get("/api/v1/system/roi/dashboard?time_range=today")
    assert resp.status_code == 200
    data = resp.json()

    assert data["time_range"] == "today"
    assert data["total_hours_saved"] > 0
    assert data["total_monetary_saved_usd"] > 0
    assert data["total_compute_cost_usd"] > 0
    assert data["net_roi_multiplier"] > 1.0
    assert data["hourly_rate_baseline_usd"] == 35.0
    assert len(data["categories_breakdown"]) == 6
    assert data["recent_digest"] is not None
    assert data["recent_digest"]["week_label"].startswith("Week")


@pytest.mark.asyncio
async def test_get_roi_dashboard_custom_hourly_rate(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.get("/api/v1/system/roi/dashboard?time_range=week&hourly_rate=60.0")
    assert resp.status_code == 200
    data = resp.json()

    assert data["time_range"] == "week"
    assert data["hourly_rate_baseline_usd"] == 60.0
    assert data["total_hours_saved"] > 50.0
    assert data["total_monetary_saved_usd"] > 2000.0


@pytest.mark.asyncio
async def test_list_high_yield_routines(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.get("/api/v1/system/roi/routines")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data) >= 4
    first_routine = data[0]
    assert "routine_id" in first_routine
    assert "title_zh" in first_routine
    assert "title_en" in first_routine
    assert first_routine["estimated_minutes_saved"] > 0
    assert first_routine["typical_roi_multiplier"] > 50.0
    assert len(first_routine["preset_prompt"]) > 10


@pytest.mark.asyncio
async def test_calculate_custom_roi_post(async_client: httpx.AsyncClient) -> None:
    payload = {
        "category_key": "code_refactor",
        "task_count": 4,
        "actual_compute_cost_usd": 0.25,
        "hourly_rate_usd": 50.0,
    }
    resp = await async_client.post("/api/v1/system/roi/calculate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["category_key"] == "code_refactor"
    assert data["task_count"] == 4
    # code_refactor benchmark is 2.5h per task -> 4 * 2.5 = 10.0h
    assert data["estimated_hours_saved"] == 10.0
    # 10.0h * 50.0 USD/h = 500.0 USD
    assert data["estimated_saved_value_usd"] == 500.0
    assert data["actual_compute_cost_usd"] == 0.25
    # 500.0 / 0.25 = 2000.0x ROI
    assert data["roi_multiplier"] == 2000.0
