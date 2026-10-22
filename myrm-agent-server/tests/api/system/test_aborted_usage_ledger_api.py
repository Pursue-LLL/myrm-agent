"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.aborted_usage_ledger_api::router

[OUTPUT]:
- Pytest verification for canonical usage ledger preventing pseudo-free zero-token representation on aborted calls.

[POS]:
tests/api/system/test_aborted_usage_ledger_api.py — 中止辅助调用记 usage-unknown REST API 单元测试。
"""

from collections.abc import AsyncGenerator
from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.aborted_usage_ledger_api import router as ledger_router

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
async def test_aborted_usage_ledger_api_lifecycle(async_client: httpx.AsyncClient) -> None:
    session_id = "sess-api-001"

    # 1. Reset state
    reset_resp = await async_client.post("/api/v1/system/aborted-usage-ledger/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"status": "reset_completed"}

    # 2. Record normal completed primary call
    r1 = await async_client.post(
        "/api/v1/system/aborted-usage-ledger/record",
        json={
            "session_id": session_id,
            "task_id": "task-primary-1",
            "call_kind": "primary",
            "call_status": "completed",
            "prompt_tokens": 400,
            "completion_tokens": 150,
            "cost_usd": 0.012,
        },
    )
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1["usage_availability"] == "exact"
    assert data1["prompt_tokens"] == 400
    assert data1["completion_tokens"] == 150
    assert data1["total_tokens"] == 550
    assert data1["cost_usd"] == 0.012

    # 3. Record aborted auxiliary compaction call without usage payload
    r2 = await async_client.post(
        "/api/v1/system/aborted-usage-ledger/record",
        json={
            "session_id": session_id,
            "task_id": "task-compaction-2",
            "call_kind": "auxiliary_compaction",
            "call_status": "aborted",
            "provider_raw_status": "client_cancelled",
        },
    )
    assert r2.status_code == 200
    data2 = r2.json()
    # Must NOT fill 0 tokens or 0.0 cost
    assert data2["usage_availability"] == "usage-unknown"
    assert data2["prompt_tokens"] is None
    assert data2["completion_tokens"] is None
    assert data2["total_tokens"] is None
    assert data2["cost_usd"] is None
    assert data2["call_status"] == "aborted"

    # 4. Retrieve ledger summary
    summary_resp = await async_client.get(
        "/api/v1/system/aborted-usage-ledger/summary",
        params={"session_id": session_id},
    )
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert summary_data["total_calls"] == 2
    assert summary_data["known_usage_calls"] == 1
    assert summary_data["unknown_usage_calls"] == 1
    assert summary_data["aborted_calls_count"] == 1
    assert summary_data["total_known_prompt_tokens"] == 400
    assert summary_data["total_known_completion_tokens"] == 150
    assert summary_data["total_known_tokens"] == 550
    assert summary_data["total_known_cost_usd"] == 0.012
    assert summary_data["unknown_risk_flag"] is True

    # 5. Filter records by usage_availability
    records_unknown = await async_client.get(
        "/api/v1/system/aborted-usage-ledger/records",
        params={"session_id": session_id, "usage_availability": "usage-unknown"},
    )
    assert records_unknown.status_code == 200
    rows_unknown = records_unknown.json()
    assert len(rows_unknown) == 1
    assert rows_unknown[0]["task_id"] == "task-compaction-2"

    # 6. Invalid call parameters
    bad_kind = await async_client.post(
        "/api/v1/system/aborted-usage-ledger/record",
        json={
            "session_id": session_id,
            "task_id": "task-err",
            "call_kind": "invalid_kind_123",
        },
    )
    assert bad_kind.status_code == 400

    bad_status = await async_client.post(
        "/api/v1/system/aborted-usage-ledger/record",
        json={
            "session_id": session_id,
            "task_id": "task-err",
            "call_status": "unknown_status_999",
        },
    )
    assert bad_status.status_code == 400
