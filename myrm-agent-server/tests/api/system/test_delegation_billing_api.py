"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.delegation_billing_api::router

[OUTPUT]:
- Pytest verification for external delegation billing divergence, subscription savings, and summary REST endpoints.

[POS]:
tests/api/system/test_delegation_billing_api.py — 外部委托用量透明化与计费分轨 API 单元测试。
"""

from collections.abc import AsyncGenerator
from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.delegation_billing_api import router as del_router

test_app = FastAPI()
test_app.include_router(del_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_delegation_billing_api_lifecycle(async_client: httpx.AsyncClient) -> None:
    # 1. Reset state
    reset_resp = await async_client.post("/api/v1/system/delegation-billing/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"status": "reset"}

    # 2. Record subscription delegation
    sub_resp = await async_client.post(
        "/api/v1/system/delegation-billing/record",
        json={
            "session_id": "sess-sub-001",
            "source": "delegate:claude-3-5",
            "input_tokens": 1200,
            "output_tokens": 600,
            "auth_mode": "subscription",
        },
    )
    assert sub_resp.status_code == 200
    sub_data = sub_resp.json()
    assert sub_data["session_id"] == "sess-sub-001"
    assert sub_data["source"] == "delegate:claude-3-5"
    assert sub_data["total_tokens"] == 1800
    assert sub_data["auth_mode"] == "subscription"
    assert sub_data["billable"] is False
    assert sub_data["billed_cost_usd"] == 0.0
    assert sub_data["estimated_savings_usd"] > 0.0

    # 3. Record api_key delegation
    api_resp = await async_client.post(
        "/api/v1/system/delegation-billing/record",
        json={
            "session_id": "sess-api-002",
            "source": "delegate:codex",
            "input_tokens": 2500,
            "output_tokens": 800,
            "auth_mode": "api_key",
            "cost_usd": 0.035,
        },
    )
    assert api_resp.status_code == 200
    api_data = api_resp.json()
    assert api_data["session_id"] == "sess-api-002"
    assert api_data["auth_mode"] == "api_key"
    assert api_data["billable"] is True
    assert api_data["billed_cost_usd"] == pytest.approx(0.035, abs=1e-5)
    assert api_data["estimated_savings_usd"] == 0.0

    # 4. Check summary
    summary_resp = await async_client.get("/api/v1/system/delegation-billing/summary")
    assert summary_resp.status_code == 200
    sum_data = summary_resp.json()
    assert sum_data["total_delegations"] == 2
    assert sum_data["subscription_calls_count"] == 1
    assert sum_data["api_key_calls_count"] == 1
    assert sum_data["total_subscription_tokens"] == 1800
    assert sum_data["total_api_key_tokens"] == 3300
    assert sum_data["total_estimated_savings_usd"] > 0.0
    assert sum_data["total_billed_cost_usd"] == pytest.approx(0.035, abs=1e-5)
    assert len(sum_data["sources"]) == 2

    # 5. Query records with session filter
    records_sub = await async_client.get(
        "/api/v1/system/delegation-billing/records",
        params={"session_id": "sess-sub-001"},
    )
    assert records_sub.status_code == 200
    sub_recs = records_sub.json()
    assert len(sub_recs) == 1
    assert sub_recs[0]["session_id"] == "sess-sub-001"
