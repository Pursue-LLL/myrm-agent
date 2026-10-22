"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.composite_usage_ledger_api::router

[OUTPUT]:
- Pytest verification for composite session model usage ledger and dual-track reconciliation REST endpoints.

[POS]:
tests/api/system/test_composite_usage_ledger_api.py — 六维复合账本与双轨对账 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.composite_usage_ledger_api import router as ledger_router

test_app = FastAPI()
test_app.include_router(ledger_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_composite_usage_ledger_api_flow(async_client: httpx.AsyncClient) -> None:
    # 1. Reset all records
    reset_resp = await async_client.post("/api/v1/system/composite-usage-ledger/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"ok": True}

    # 2. Check initial clean summary
    init_sum = await async_client.get("/api/v1/system/composite-usage-ledger/summary")
    assert init_sum.status_code == 200
    sum_data = init_sum.json()
    assert sum_data["total_records"] == 0
    assert sum_data["total_calls"] == 0
    assert sum_data["total_estimated_usd"] == 0.0

    # 3. Record usage for main_turn
    r1_resp = await async_client.post(
        "/api/v1/system/composite-usage-ledger/record",
        json={
            "session_id": "session_api_01",
            "model": "claude-3-7-sonnet",
            "billing_provider": "anthropic",
            "billing_base_url": "https://api.anthropic.com/v1",
            "billing_mode": "standard",
            "task": "main_turn",
            "input_tokens": 1200,
            "output_tokens": 400,
            "cache_read_tokens": 800,
            "estimated_cost_usd": 0.025,
            "actual_cost_usd": 0.0,
        },
    )
    assert r1_resp.status_code == 200
    r1_data = r1_resp.json()
    assert r1_data["session_id"] == "session_api_01"
    assert r1_data["task"] == "main_turn"
    assert r1_data["api_call_count"] == 1
    assert r1_data["cost_status"] == "ESTIMATED_ONLY"

    # 4. Record usage for distinct task under same session: artifact_compile
    r2_resp = await async_client.post(
        "/api/v1/system/composite-usage-ledger/record",
        json={
            "session_id": "session_api_01",
            "model": "claude-3-7-sonnet",
            "billing_provider": "anthropic",
            "billing_base_url": "https://api.anthropic.com/v1",
            "billing_mode": "standard",
            "task": "artifact_compile",
            "input_tokens": 3000,
            "output_tokens": 1500,
            "estimated_cost_usd": 0.060,
            "actual_cost_usd": 0.0,
        },
    )
    assert r2_resp.status_code == 200
    assert r2_resp.json()["task"] == "artifact_compile"

    # 5. Reconcile invoice for main_turn within tolerance (actual 0.026 vs estimated 0.025 -> 4% drift -> RECONCILED)
    rec_resp = await async_client.post(
        "/api/v1/system/composite-usage-ledger/reconcile",
        json={
            "session_id": "session_api_01",
            "model": "claude-3-7-sonnet",
            "billing_provider": "anthropic",
            "billing_base_url": "https://api.anthropic.com/v1",
            "billing_mode": "standard",
            "task": "main_turn",
            "actual_cost_usd": 0.026,
        },
    )
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()
    assert rec_data["cost_status"] == "RECONCILED"
    assert rec_data["actual_cost_usd"] == 0.026

    # 6. Reconcile invoice for artifact_compile with discrepancy (actual 0.090 vs estimated 0.060 -> 50% drift -> DISCREPANCY_ALERT)
    rec2_resp = await async_client.post(
        "/api/v1/system/composite-usage-ledger/reconcile",
        json={
            "session_id": "session_api_01",
            "model": "claude-3-7-sonnet",
            "billing_provider": "anthropic",
            "billing_base_url": "https://api.anthropic.com/v1",
            "billing_mode": "standard",
            "task": "artifact_compile",
            "actual_cost_usd": 0.090,
        },
    )
    assert rec2_resp.status_code == 200
    assert rec2_resp.json()["cost_status"] == "DISCREPANCY_ALERT"

    # 7. Check query records and summary
    records_resp = await async_client.get(
        "/api/v1/system/composite-usage-ledger/records",
        params={"session_id": "session_api_01"},
    )
    assert records_resp.status_code == 200
    assert len(records_resp.json()) == 2

    summary_resp = await async_client.get(
        "/api/v1/system/composite-usage-ledger/summary",
        params={"session_id": "session_api_01"},
    )
    assert summary_resp.status_code == 200
    s_data = summary_resp.json()
    assert s_data["total_records"] == 2
    assert s_data["total_calls"] == 2
    assert s_data["reconciled_records_count"] == 1
    assert s_data["discrepancy_records_count"] == 1
    assert "main_turn" in s_data["task_spend_distribution"]
    assert "artifact_compile" in s_data["task_spend_distribution"]

    # 8. Reset for specific session
    r_reset = await async_client.post(
        "/api/v1/system/composite-usage-ledger/reset",
        json={"session_id": "session_api_01"},
    )
    assert r_reset.status_code == 200
    empty_records = await async_client.get(
        "/api/v1/system/composite-usage-ledger/records",
        params={"session_id": "session_api_01"},
    )
    assert len(empty_records.json()) == 0
