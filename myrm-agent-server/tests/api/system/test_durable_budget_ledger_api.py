"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.durable_budget_ledger_api::router

[OUTPUT]:
- Pytest verification for durable budget spend recovery and actual-billed reconciliation REST endpoints.

[POS]:
tests/api/system/test_durable_budget_ledger_api.py — 持久化每日预算账本 REST API 单元测试。
"""

from collections.abc import AsyncGenerator
from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.durable_budget_ledger_api import router as ledger_router

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
async def test_durable_budget_ledger_api_lifecycle(async_client: httpx.AsyncClient) -> None:
    session_id = "sess-budget-api-1"

    # 1. Reset state
    reset_resp = await async_client.post("/api/v1/system/durable-budget-ledger/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"status": "reset_completed"}

    # 2. Record Turn 1 (active branch)
    r1 = await async_client.post(
        "/api/v1/system/durable-budget-ledger/record-spend",
        json={
            "cost_usd": 0.020,
            "category": "chat",
            "session_id": session_id,
            "message_id": "msg-active-1",
            "is_active_branch": True,
        },
    )
    assert r1.status_code == 200
    assert r1.json()["cost_usd"] == 0.020
    assert r1.json()["is_active_branch"] is True

    # 3. Record Turn 2 (which gets retried/rewound later)
    r2 = await async_client.post(
        "/api/v1/system/durable-budget-ledger/record-spend",
        json={
            "cost_usd": 0.015,
            "category": "chat",
            "session_id": session_id,
            "message_id": "msg-rewound-2",
            "is_active_branch": True,
        },
    )
    assert r2.status_code == 200

    # 4. Mark Turn 2 as discarded upon retry
    discard_resp = await async_client.post(
        "/api/v1/system/durable-budget-ledger/mark-discarded",
        json={"message_id": "msg-rewound-2"},
    )
    assert discard_resp.status_code == 200
    assert discard_resp.json()["updated_count"] == 1

    # 5. Record background auxiliary/cache spend
    r3 = await async_client.post(
        "/api/v1/system/durable-budget-ledger/record-spend",
        json={
            "cost_usd": 0.005,
            "category": "cache_warm",
            "is_active_branch": True,
        },
    )
    assert r3.status_code == 200

    # 6. Verify today's spent recovered: 0.020 + 0.015 + 0.005 = 0.040 USD
    today_resp = await async_client.get("/api/v1/system/durable-budget-ledger/today-spent")
    assert today_resp.status_code == 200
    assert today_resp.json()["today_spent_usd"] == 0.040

    # 7. Verify recovery summary with surviving messages (surviving message = only msg-active-1 = 0.020)
    summary_resp = await async_client.get(
        "/api/v1/system/durable-budget-ledger/recovery-summary",
        params={"surviving_message_cost_usd": 0.020},
    )
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert summary_data["total_durable_cost_usd"] == 0.040
    assert summary_data["total_surviving_message_cost_usd"] == 0.020
    assert summary_data["discarded_branch_cost_usd"] == 0.015
    assert summary_data["budget_underestimation_gap_usd"] == 0.020

    # 8. Verify session actual billed statement
    stmt_resp = await async_client.get(f"/api/v1/system/durable-budget-ledger/session-billed/{session_id}")
    assert stmt_resp.status_code == 200
    stmt_data = stmt_resp.json()
    assert stmt_data["actual_billed_cost_usd"] == 0.035  # 0.020 + 0.015
    assert stmt_data["visible_branch_cost_usd"] == 0.020  # only msg-active-1
    assert stmt_data["discarded_diff_cost_usd"] == 0.015  # msg-rewound-2

    # 9. Invalid category validation
    bad_cat = await async_client.post(
        "/api/v1/system/durable-budget-ledger/record-spend",
        json={"cost_usd": 0.01, "category": "non_existent_category"},
    )
    assert bad_cat.status_code == 400
